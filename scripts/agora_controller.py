#!/usr/bin/env python3
"""Bounded, auditable AGORA controller; no model-supplied commands or paths."""
import argparse
import json
import math
import os
import subprocess
from pathlib import Path

from agora_decide import ACTIONS, decide
from agora_profile import validate_profile

SCENARIOS = ('clean','adapter','quality','combined')


def path_for(scenario, action):
    if scenario not in SCENARIOS or action not in ('raw', *ACTIONS[1:]):
        raise ValueError('Invalid scenario/action')
    return Path('results/challenges') / scenario / action / 'profile.json'


def run_target(path, cores):
    # argv list prevents arbitrary shell execution; path only from strict enumerations.
    command = ['snakemake', '--cores', str(cores), str(path)]
    print('Executing:', ' '.join(command), flush=True)
    subprocess.run(command, check=True)
    if not path.is_file():
        raise RuntimeError('Snakemake target missing: ' + str(path))


def load_profile(path):
    if path.stat().st_size > 12000:
        raise ValueError('QC profile unexpectedly large')
    return validate_profile(json.loads(path.read_text(encoding='utf8')))


def acceptable(base, candidate):
    """Pre-registered, reference-free safety screen; NOT a correctness test."""
    a, b = base['assembly_qc'], candidate['assembly_qc']
    if b['assembly_length_bp'] < .98 * a['assembly_length_bp']:
        return False, 'Assembly length fell >2%'
    if b['n50_bp'] < .90 * a['n50_bp']:
        return False, 'N50 fell >10%'
    if b['contig_count'] > 1.1 * a['contig_count']:
        return False, 'Contig count increased >10%'
    if (b['n50_bp'] >= 1.05 * a['n50_bp'] or
            b['contig_count'] <= .95 * a['contig_count']):
        return True, 'Improved contiguity proxy with safety guards'
    sig_a, sig_b = base['artifact_signals'], candidate['artifact_signals']
    motif_improved = sig_a['adapter_motif_end_percent'] - sig_b['adapter_motif_end_percent'] >= 5
    tail_improved = sig_a['tail_bases_below_q20_percent'] - sig_b['tail_bases_below_q20_percent'] >= 5
    if (motif_improved or tail_improved) and b['n50_bp'] >= .98 * a['n50_bp']:
        return True, 'Reduced read-artifact signal without major contiguity loss'
    return False, 'No sufficiently clear reference-free improvement'


def quality_score(baseline, candidate):
    a, b = baseline['assembly_qc'], candidate['assembly_qc']
    # Frozen selection proxy; avoid post-hoc reference-informed tuning.
    n50 = math.log(b['n50_bp'] / a['n50_bp'])
    count = math.log(a['contig_count'] / b['contig_count'])
    sig_a, sig_b = baseline['artifact_signals'], candidate['artifact_signals']
    artifact = .002 * (sig_a['adapter_motif_end_percent'] - sig_b['adapter_motif_end_percent'])
    tail = .001 * (sig_a['tail_bases_below_q20_percent'] - sig_b['tail_bases_below_q20_percent'])
    return round(n50 + .3 * count + artifact + tail, 6)


def summary(p):
    # Explicit numeric whitelist in history; never transmit sample names or truth.
    return {
        'n50_bp': p['assembly_qc']['n50_bp'],
        'contig_count': p['assembly_qc']['contig_count'],
        'assembly_length_bp': p['assembly_qc']['assembly_length_bp'],
        'q30_percent': p['read_qc']['q30_percent'],
        'adapter_motif_end_percent': p['artifact_signals']['adapter_motif_end_percent'],
        'tail_bases_below_q20_percent': p['artifact_signals']['tail_bases_below_q20_percent'],
    }


def experiment(scenario, backend, mode='iterative', max_steps=2, cores=4,
               model=None, ensure_standard=True, execute=True):
    if scenario not in SCENARIOS or backend not in ('rule','mock','llm') or mode not in ('zero','iterative'):
        raise ValueError('Invalid experiment selection')
    if not 1 <= max_steps <= 3:
        raise ValueError('Iteration budget must be 1-3')
    if backend == 'llm' and execute and not model:
        raise ValueError('Set --model to an ID from SoCLaaS /v1/models (or export SOCLAAS_MODEL)')
    budget = 1 if mode == 'zero' else max_steps
    targets = [path_for(scenario, 'raw')]
    if ensure_standard:
        targets.append(path_for(scenario, 'fastp_default'))
    if not execute:
        return {'dry_plan': [str(x) for x in targets], 'max_steps': budget,
                'note': 'After these, controller selects only whitelisted trial targets'}
    for target in targets:
        run_target(target, cores)
    baseline = load_profile(targets[0])
    current = baseline
    winner = 'raw'
    winner_score = 0.0
    history = []
    decisions = []
    for step in range(budget):
        decision = decide(backend, current, history, model, summary(baseline))
        action = decision['action']
        decisions.append(decision)
        if action == 'stop':
            break
        if action in {x['action'] for x in history}:
            raise ValueError('Policy proposed duplicate action; refusing to rerun')
        target = path_for(scenario, action)  # only fixed, approved actions
        run_target(target, cores)
        candidate = load_profile(target)
        accepted, reason = acceptable(baseline, candidate)
        score = quality_score(baseline, candidate) if accepted else None
        history.append({'action': action, 'result': summary(candidate),
                        'acceptable': accepted, 'explanation': reason})
        if accepted and score > winner_score:
            winner_score = score
            winner = action
        current = candidate
    result = {
        'evaluation_status': 'reference_free_only',
        'backend': backend, 'mode': mode, 'scenario': scenario,  # audit file ONLY, not model context
        'model': model if backend == 'llm' else None,
        'provider': 'soclaas' if backend == 'llm' else None,
        'original': summary(baseline),
        'attempts': history,
        'decisions': decisions,
        'selected_action': winner,
        'selected_score': winner_score,
        'standard_fastp_comparator': str(path_for(scenario, 'fastp_default')) if ensure_standard else None,
        'note': 'Selection is a heuristic from reference-free metrics; correctness must be evaluated separately',
    }
    out = Path('results/agent_runs') / scenario / f'{backend}_{mode}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'saved': str(out), 'selected_action': winner, 'attempts': len(history)}, indent=2))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--scenario', choices=SCENARIOS, default='combined')
    p.add_argument('--backend', choices=['rule','mock','llm'], default='mock')
    p.add_argument('--mode', choices=['zero','iterative'], default='iterative')
    p.add_argument('--max-steps', type=int, default=2)
    p.add_argument('--cores', type=int, default=4)
    p.add_argument('--model', default=os.environ.get('SOCLAAS_MODEL'),
                   help='Exact SoCLaaS model ID (or SOCLAAS_MODEL env var)')
    p.add_argument('--no-standard', action='store_true')
    p.add_argument('--dry-plan', action='store_true')
    a = p.parse_args()
    info = experiment(a.scenario, a.backend, a.mode, a.max_steps, a.cores,
                      a.model, not a.no_standard, not a.dry_plan)
    if a.dry_plan:
        print(json.dumps(info, indent=2))
