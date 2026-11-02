#!/usr/bin/env python3
"""Benchmark-only descriptive summary across isolated AGORA held-out seeds.

Never import from agent decision/prompt/controller code. Requires completed
agora_evaluate.py runs in results/holdouts/seed_*/.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean, median

SCENARIOS = ('clean', 'adapter', 'quality', 'combined')
STRATEGIES = ('raw', 'fastp_default', 'rule_zero', 'rule_iterative',
              'llm_zero', 'llm_iterative', 'clean_control')
AGENTS = ('rule_zero', 'rule_iterative', 'llm_zero', 'llm_iterative')
METRICS = {
    'NGA50': 'nga50_bp',
    'N50': 'n50_bp',
    '# contigs': 'contig_count',
    '# misassemblies': 'misassemblies',
    'Genome fraction (%)': 'genome_fraction_percent',
    '# mismatches per 100 kbp': 'mismatches_per_100kb',
    '# indels per 100 kbp': 'indels_per_100kb',
}
TRUTH = {'clean': 'no_strong_signal', 'adapter': 'adapter_signal',
         'quality': 'quality_signal', 'combined': 'mixed_signal'}
FIELDS = ('seed', 'scenario', 'strategy', 'selected_action', 'initial_diagnosis',
          'category_match', 'trial_count', 'model',
          *METRICS.values(), 'nga50_delta_vs_fastp_percent',
          'mismatch_delta_vs_fastp_per_100kb')


def parsed_num(x):
    if x is None or x == '' or x == '-':
        return None
    try:
        return float(str(x).replace(',', ''))
    except (TypeError, ValueError):
        return None


def collect(root: Path, seeds: list[int]):
    rows, warnings = [], []
    for seed in seeds:
        wk = root / 'results/holdouts' / f'seed_{seed}'
        if not (wk / 'holdout_manifest.json').is_file():
            warnings.append(f'Missing prepared workspace: {wk}')
            continue
        for scenario in SCENARIOS:
            path = wk / 'results/evaluation/challenges' / scenario / 'comparison.json'
            if not path.is_file():
                warnings.append(f'Missing evaluation: seed {seed}, {scenario}')
                continue
            comp = json.loads(path.read_text(encoding='utf8'))
            metrics = comp.get('metrics', {})
            fastp_n = parsed_num(metrics.get('NGA50', {}).get('fastp_default'))
            fastp_m = parsed_num(metrics.get('# mismatches per 100 kbp', {}).get('fastp_default'))
            for strategy in STRATEGIES:
                if strategy not in comp.get('strategies', []):
                    if strategy != 'clean_control':
                        warnings.append(f'Missing strategy: seed {seed}, {scenario}, {strategy}')
                    continue
                row = {'seed': seed, 'scenario': scenario, 'strategy': strategy,
                       'selected_action': strategy, 'initial_diagnosis': '',
                       'category_match': '', 'trial_count': '', 'model': ''}
                for raw_name, field in METRICS.items():
                    row[field] = parsed_num(metrics.get(raw_name, {}).get(strategy))
                    if row[field] is None:
                        warnings.append(f'Missing metric {raw_name}: seed {seed}, {scenario}, {strategy}')
                if strategy in AGENTS:
                    log = wk / 'results/agent_runs' / scenario / f'{strategy}.json'
                    if not log.is_file():
                        warnings.append(f'Missing agent log: seed {seed}, {scenario}, {strategy}')
                    else:
                        if log.stat().st_mtime > path.stat().st_mtime + 2:
                            warnings.append(f'STALE evaluation: seed {seed}, {scenario}, {strategy}')
                        audit = json.loads(log.read_text(encoding='utf8'))
                        decisions = audit.get('decisions') or []
                        first = decisions[0].get('diagnosis', '') if decisions else ''
                        row.update(selected_action=audit.get('selected_action', ''),
                                   initial_diagnosis=first,
                                   category_match='yes' if first == TRUTH[scenario] else 'no' if first else '',
                                   trial_count=len(audit.get('attempts') or []),
                                   model=audit.get('model') or '')
                nga = row.get('nga50_bp')
                mismatch = row.get('mismatches_per_100kb')
                row['nga50_delta_vs_fastp_percent'] = (
                    round((nga / fastp_n - 1) * 100, 3)
                    if nga is not None and fastp_n and strategy != 'clean_control' else None)
                row['mismatch_delta_vs_fastp_per_100kb'] = (
                    round(mismatch - fastp_m, 3)
                    if mismatch is not None and fastp_m is not None and strategy != 'clean_control' else None)
                rows.append(row)
    return rows, warnings


def fmt(values, decimals=1):
    if not values:
        return '—'
    lo, hi = min(values), max(values)
    return f'{median(values):,.{decimals}f} [{lo:,.{decimals}f}, {hi:,.{decimals}f}]'


def report(rows, warnings, seeds):
    lines = [
        '# AGORA — Held-out seed replication summary', '',
        '**BENCHMARK-ONLY. Never send injected labels or reference-based metrics to agents.**', '',
        'This analysis changes only corruption placement using different random seeds; '
        'the synthetic adapter and sequencing-error rates remain unchanged. '
        'Results are descriptive, not evidence of statistical significance.', '',
        f'Seeds requested: {", ".join(map(str, seeds))}.', '',
        'Numbers are median [minimum, maximum] across available seeds; missing '
        'runs are excluded and flagged below.', '',
    ]
    for scenario in SCENARIOS:
        subset = [r for r in rows if r['scenario'] == scenario]
        lines.extend((f'## {scenario.title()}', '',
                      '| Strategy | n | NGA50 (bp) | Mismatches / 100 kbp | Δ NGA50 vs fastp (%) | Δ mismatch rate vs fastp |',
                      '|---|---:|---:|---:|---:|---:|'))
        for strategy in STRATEGIES:
            ss = [r for r in subset if r['strategy'] == strategy]
            if not ss:
                continue
            values = lambda k: [float(r[k]) for r in ss if r.get(k) is not None]
            lines.append('| ' + ' | '.join((
                strategy, str(len(ss)), fmt(values('nga50_bp'), 0),
                fmt(values('mismatches_per_100kb'), 2),
                fmt(values('nga50_delta_vs_fastp_percent'), 2),
                fmt(values('mismatch_delta_vs_fastp_per_100kb'), 2),
            )) + ' |')
        lines.append('')
    lines.extend(('## Diagnosis category agreements', '',
                  '| Strategy | Matches | Scenarios evaluated across seeds |',
                  '|---|---:|---:|'))
    for strategy in AGENTS:
        ss = [r for r in rows if r['strategy'] == strategy and r['category_match']]
        wins = sum(r['category_match'] == 'yes' for r in ss)
        lines.append(f'| {strategy} | {wins} | {len(ss)} |')
    lines.extend(('', '## Data checks', ''))
    lines.extend(f'- {w}' for w in warnings) if warnings else lines.append('- No missing or stale files detected by basic checks.')
    lines.extend(('', '## Limitations', '',
                  '- Metrics are correlated, and an improvement in mismatch rate can coincide with worse contiguity.',
                  '- A controller-accepted action is not necessarily the best reference-based assembly.',
                  '- No agent should have access to the benchmark reference or synthetic scenario label.',
                  '- Model stochasticity and infrastructure variation are not controlled solely by random seed.',
                  '- These tests vary corruption placement, not error severity or bacterial species.', ''))
    return '\n'.join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('.'))
    p.add_argument('--seeds', type=int, nargs='+', required=True)
    p.add_argument('--output-dir', type=Path, default=None)
    a = p.parse_args()
    root = a.root.resolve()
    rows, warnings = collect(root, a.seeds)
    out = a.output_dir.resolve() if a.output_dir else root / 'results/evaluation/heldout_summary'
    out.mkdir(parents=True, exist_ok=True)
    with (out / 'heldout_metrics.csv').open('w', newline='', encoding='utf8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (out / 'Heldout_Seed_Report.md').write_text(report(rows, warnings, a.seeds), encoding='utf8')
    print('Wrote:', out / 'heldout_metrics.csv')
    print('Wrote:', out / 'Heldout_Seed_Report.md')
    print(f'Rows: {len(rows)}, warnings: {len(warnings)}')
    for w in warnings:
        print('WARNING:', w)


if __name__ == '__main__':
    main()
