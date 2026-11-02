#!/usr/bin/env python3
"""Independent REFERENCE-BASED QUAST; never import this module into controller."""
import argparse
import csv
import json
import subprocess
from pathlib import Path

from agora_controller import SCENARIOS

REPORT_KEYS = ('Genome fraction (%)', 'NGA50', '# misassemblies',
               '# mismatches per 100 kbp', '# indels per 100 kbp', 'N50', '# contigs')


def evaluate(scenario, reference, cores=4):
    if scenario not in SCENARIOS:
        raise ValueError('Unrecognized scenario')
    reference = Path(reference)
    if not reference.is_file():
        raise FileNotFoundError(reference)
    root = Path('results/challenges') / scenario
    variants = {
        'raw': root / 'raw/spades/contigs.fasta',
        'fastp_default': root / 'fastp_default/spades/contigs.fasta',
    }
    for backend in ('rule', 'llm'):
        for mode in ('zero', 'iterative'):
            result = Path('results/agent_runs') / scenario / f'{backend}_{mode}.json'
            if result.exists():
                selected = json.loads(result.read_text(encoding='utf8'))['selected_action']
                if selected not in ('raw','fastp_default','explicit_adapter','quality_trim','adapter_quality'):
                    raise ValueError('Unexpected action in audit')
                variants[f'{backend}_{mode}'] = root / selected / 'spades/contigs.fasta'
    # Add clean-data control if it has been run.
    clean = Path('results/challenges/clean/raw/spades/contigs.fasta')
    if clean.is_file():
        variants['clean_control'] = clean
    missing = [name for name, file in variants.items() if not file.is_file()]
    if missing:
        raise FileNotFoundError('Assemblies missing: '+', '.join(missing))
    directory = Path('results/evaluation/challenges') / scenario
    directory.mkdir(parents=True, exist_ok=True)
    cmd = ['quast.py', *[str(file) for file in variants.values()], '-r', str(reference),
           '-l', ','.join(variants), '--threads', str(cores), '-o', str(directory)]
    subprocess.run(cmd, check=True)
    report = directory / 'report.tsv'
    rows = {}
    with report.open(newline='', encoding='utf8') as handle:
        reader = csv.reader(handle, delimiter='\t')
        header = next(reader)
        if header[0] != 'Assembly':
            raise ValueError('Unexpected QUAST report')
        for row in reader:
            if row and row[0] in REPORT_KEYS:
                rows[row[0]] = {label: value for label, value in zip(header[1:], row[1:])}
    outfile = directory / 'comparison.json'
    outfile.write_text(json.dumps({'note': 'BENCHMARK ONLY — NEVER GIVEN TO AGENTS',
                                   'strategies': list(variants), 'metrics': rows}, indent=2)+'\n', encoding='utf8')
    print('Reference evaluation:', report)
    print('Summary:', outfile)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--scenario', choices=SCENARIOS, default='combined')
    ap.add_argument('--reference', required=True)
    ap.add_argument('--cores', type=int, default=4)
    a = ap.parse_args()
    evaluate(a.scenario, a.reference, a.cores)
