#!/usr/bin/env python3
"""Run AGORA held-out seeds without changing the original experiment files.

Preparation snapshots Snakefile, workflow, scripts, config and trimmed reads in an
isolated seed-specific working directory. Controller and evaluation are then run
there, preserving the unmodified reference experiment.

The model is NOT given the seed, scenario label or reference metrics. These are
runner-side audit metadata only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import yaml

SCENARIOS = ('clean', 'adapter', 'quality', 'combined')
BACKENDS = ('rule', 'llm')
MODES = ('zero', 'iterative')
ORIGINAL_SEED = 2026


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(2 ** 20), b''):
            h.update(chunk)
    return h.hexdigest()


def workspace_path(root: Path, seed: int) -> Path:
    if seed < 0 or seed > 2**32 - 1:
        raise ValueError('Seed must be a nonnegative 32-bit integer')
    if seed == ORIGINAL_SEED:
        raise ValueError('Choose a held-out seed other than the development seed 2026')
    return root / 'results' / 'holdouts' / f'seed_{seed}'


def required_source(root: Path) -> list[Path]:
    rel = [Path('Snakefile'), Path('config.yaml'),
           Path('workflow/agora_challenge.smk'),
           Path('scripts/agora_controller.py'),
           Path('scripts/agora_inject.py'),
           Path('scripts/agora_evaluate.py'),
           Path('results/trimmed/reads/R1.fastq.gz'),
           Path('results/trimmed/reads/R2.fastq.gz'),
           Path('results/trimmed/fastp/fastp.json'),
           Path('results/trimmed/fastp/fastp.html')]
    missing = [str(x) for x in rel if not (root / x).is_file()]
    if missing:
        raise FileNotFoundError('Missing AGORA project files: ' + ', '.join(missing))
    return rel


def prepare(root: Path, seed: int) -> Path:
    root = root.resolve()
    files = required_source(root)
    work = workspace_path(root, seed)
    if work.exists():
        raise FileExistsError(f'{work} already exists; refusing to overwrite held-out outputs')
    # Only create the directory after checking the project and seed.
    work.mkdir(parents=True)
    try:
        for name in ('Snakefile',):
            shutil.copy2(root / name, work / name)
        if not (root / 'workflow').is_dir() or not (root / 'scripts').is_dir():
            raise FileNotFoundError('Project workflow/ and scripts/ directories are required')
        shutil.copytree(root / 'workflow', work / 'workflow', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copytree(root / 'scripts', work / 'scripts', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        cfg = yaml.safe_load((root / 'config.yaml').read_text(encoding='utf8')) or {}
        if not isinstance(cfg, dict):
            raise ValueError('config.yaml must be a mapping')
        challenges = dict(cfg.get('agora_challenge', {}))
        challenges['seed'] = seed
        cfg['agora_challenge'] = challenges
        (work / 'config.yaml').write_text(yaml.safe_dump(cfg, sort_keys=False), encoding='utf8')

        # Copy, do NOT link, the large preprocessed read inputs. This avoids
        # accidentally overwriting original inputs if Snakemake reruns fastp.
        read_dir = work / 'results/trimmed/reads'
        read_dir.mkdir(parents=True)
        for mate in ('R1', 'R2'):
            shutil.copy2(root / f'results/trimmed/reads/{mate}.fastq.gz', read_dir / f'{mate}.fastq.gz')
        original_fastp = root / 'results/trimmed/fastp'
        if original_fastp.is_dir():
            shutil.copytree(original_fastp, work / 'results/trimmed/fastp', ignore=shutil.ignore_patterns('__pycache__'))

        # Original raw/subset reads may be needed for dependency checks, but
        # are not copied or modified. If a rule tries to write to their parent,
        # it will not be able to write through the symlinked parent of the data.
        data_dir = work / 'data'
        data_dir.mkdir(exist_ok=True)
        for source_name in ('subset',):
            source = root / 'data' / source_name
            if source.is_dir():
                (data_dir / source_name).symlink_to(source, target_is_directory=True)

        code_paths = [work / 'Snakefile', work / 'config.yaml']
        code_paths += sorted((work / 'scripts').rglob('*.py'))
        code_paths += sorted((work / 'workflow').rglob('*.smk'))
        manifest = {
            'description': 'Held-out AGORA seed; benchmark metadata must not enter model prompts',
            'seed': seed,
            'original_development_seed': ORIGINAL_SEED,
            'read_source': 'original project results/trimmed/reads (independent copies)',
            'workspace_relative_to_project': str(work.relative_to(root)),
            'snapshot_hashes': {str(p.relative_to(work)): sha256(p) for p in code_paths},
            'inputs': {str(p): {'size_bytes': (root / p).stat().st_size} for p in files if p.parts[0] == 'results'},
        }
        (work / 'holdout_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
    except Exception:
        # Cleanup only the freshly created workspace, never an existing run.
        shutil.rmtree(work)
        raise
    return work


def validate_workspace(root: Path, seed: int) -> Path:
    work = workspace_path(root.resolve(), seed)
    manifest_path = work / 'holdout_manifest.json'
    if not manifest_path.is_file():
        raise FileNotFoundError(f'No prepared held-out run: {manifest_path}')
    manifest = json.loads(manifest_path.read_text(encoding='utf8'))
    if manifest.get('seed') != seed:
        raise ValueError('Seed/manifest mismatch')
    changed = [name for name, digest in manifest['snapshot_hashes'].items()
               if not (work / name).is_file() or sha256(work / name) != digest]
    if changed:
        raise ValueError('Frozen code/config changed: ' + ', '.join(changed))
    return work


def launch(args: list[str], work: Path) -> None:
    print('Workspace:', work, flush=True)
    print('Command:', ' '.join(args), flush=True)
    subprocess.run(args, cwd=work, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'evaluate', 'status'))
    parser.add_argument('--root', type=Path, default=Path('.'), help='Original AGORA project root')
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--scenario', choices=SCENARIOS)
    parser.add_argument('--backend', choices=BACKENDS)
    parser.add_argument('--mode', choices=MODES, default='iterative')
    parser.add_argument('--model', help='SoCLaaS model ID; defaults to SOCLAAS_MODEL')
    parser.add_argument('--reference', type=Path, help='Reference FASTA; benchmark evaluation only')
    parser.add_argument('--cores', type=int, default=4)
    parser.add_argument('--max-steps', type=int, default=2)
    a = parser.parse_args()
    root = a.root.resolve()
    if a.cores < 1 or a.max_steps not in (1, 2, 3):
        parser.error('cores must be >=1 and max-steps 1 to 3')
    if a.command == 'prepare':
        w = prepare(root, a.seed)
        print('Prepared frozen held-out workspace:', w)
        return
    work = validate_workspace(root, a.seed)
    if a.command == 'status':
        for scenario in SCENARIOS:
            for backend in BACKENDS:
                for mode in MODES:
                    path = work / 'results/agent_runs' / scenario / f'{backend}_{mode}.json'
                    print(f'{scenario:8} {backend:5} {mode:9} {"done" if path.is_file() else "pending"}')
        return
    if not a.scenario:
        parser.error(f'{a.command} requires --scenario')
    if a.command == 'run':
        if not a.backend:
            parser.error('run requires --backend')
        model = a.model or os.environ.get('SOCLAAS_MODEL')
        if a.backend == 'llm' and not model:
            parser.error('LLM runs require --model or SOCLAAS_MODEL')
        # Avoid accidental overwrite of a completed audit. Failed attempts
        # without a completed audit can be retried.
        output = work / 'results/agent_runs' / a.scenario / f'{a.backend}_{a.mode}.json'
        if output.exists():
            raise FileExistsError(f'{output} already exists; refusing to overwrite the audit')
        argv = [sys.executable, 'scripts/agora_controller.py', '--scenario', a.scenario,
                '--backend', a.backend, '--mode', a.mode, '--cores', str(a.cores),
                '--max-steps', str(a.max_steps)]
        if a.backend == 'llm':
            argv.extend(['--model', model])
        launch(argv, work)
    elif a.command == 'evaluate':
        if not a.reference:
            parser.error('evaluate requires --reference')
        ref = (a.reference if a.reference.is_absolute() else root / a.reference).resolve()
        if not ref.is_file():
            raise FileNotFoundError(ref)
        launch([sys.executable, 'scripts/agora_evaluate.py', '--scenario', a.scenario,
                '--reference', str(ref), '--cores', str(a.cores)], work)


if __name__ == '__main__':
    main()
