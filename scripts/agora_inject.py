#!/usr/bin/env python3
"""Deterministically inject synthetic adapter read-through and sequencing errors.

NOTE: benchmark metadata is NEVER used as agent input.
"""
import argparse
import gzip
import json
import random
from itertools import zip_longest
from pathlib import Path

ADAPTER_R1 = 'AGATCGGAAGAGCACACGTCTGAACTCCAGTCA'
ADAPTER_R2 = 'AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT'


def fastq_records(file_path):
    with gzip.open(file_path, 'rt', encoding='ascii') as handle:
        while True:
            h = handle.readline()
            if not h:
                return
            s, p, q = handle.readline(), handle.readline(), handle.readline()
            if not s or not p or not q or not h.startswith('@') or not p.startswith('+'):
                raise ValueError('Truncated or invalid FASTQ: ' + str(file_path))
            s, q = s.strip().upper(), q.strip()
            if len(s) != len(q):
                raise ValueError('Sequence/quality mismatch in ' + str(file_path))
            yield h.strip(), s, p.strip(), q


def read_id(h):
    return h[1:].split()[0].removesuffix('/1').removesuffix('/2')


def mutate(s, q, adapter, rng, with_adapter, with_error):
    seq = list(s)
    qual = list(q)
    if with_adapter:
        n = min(len(s) - 1, rng.randint(12, 28), len(adapter))
        if n > 0:
            seq[-n:] = list(adapter[:n])
            # Simulated adapter bases get consistent, moderate Q values.
            qual[-n:] = ['5'] * n  # Q20
    if with_error:
        n = min(25, len(seq))
        for idx in range(len(seq) - n, len(seq)):
            qual[idx] = '+'  # Q10
            if rng.random() < 0.10:
                choices = 'ACGT'.replace(seq[idx], '')
                seq[idx] = rng.choice(choices)
    return ''.join(seq), ''.join(qual)


def generate(r1, r2, out1, out2, metadata, scenario, seed=2026, max_pairs=600000,
             adapter_rate=.25, error_rate=.35):
    if scenario not in ('clean', 'adapter', 'quality', 'combined'):
        raise ValueError('Unknown scenario')
    if not (0 <= adapter_rate <= 1 and 0 <= error_rate <= 1):
        raise ValueError('Rates must be between 0 and 1')
    rng = random.Random(seed)
    out1, out2, metadata = map(Path, (out1, out2, metadata))
    for target in (out1, out2, metadata):
        target.parent.mkdir(parents=True, exist_ok=True)
    counts = {'read_pairs': 0, 'adapter_affected_reads': 0, 'error_affected_reads': 0}
    # Output files are written before the Snakemake job declares success.
    with gzip.open(out1, 'wt', encoding='ascii') as f1, gzip.open(out2, 'wt', encoding='ascii') as f2:
        for left, right in zip_longest(fastq_records(r1), fastq_records(r2)):
            if left is None or right is None:
                raise ValueError('R1/R2 read counts differ')
            if read_id(left[0]) != read_id(right[0]):
                raise ValueError('R1/R2 read IDs differ')
            for record, adapter, out in ((left, ADAPTER_R1, f1), (right, ADAPTER_R2, f2)):
                a = scenario in ('adapter', 'combined') and rng.random() < adapter_rate
                e = scenario in ('quality', 'combined') and rng.random() < error_rate
                s, q = mutate(record[1], record[3], adapter, rng, a, e)
                out.write(f'{record[0]}\n{s}\n{record[2]}\n{q}\n')
                counts['adapter_affected_reads'] += int(a)
                counts['error_affected_reads'] += int(e)
            counts['read_pairs'] += 1
            if max_pairs and counts['read_pairs'] >= max_pairs:
                break
    if not counts['read_pairs']:
        raise ValueError('No reads processed')
    result = {'scenario': scenario, 'seed': seed, 'max_pairs': max_pairs,
              'adapter_probability_per_read': adapter_rate if scenario in ('adapter', 'combined') else 0,
              'quality_error_probability_per_read': error_rate if scenario in ('quality', 'combined') else 0,
              'method': 'synthetic tail replacement plus Q10 and substitutions on selected reads',
              'benchmark_only': 'DO NOT supply this file to any agent', **counts}
    metadata.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--r1', required=True)
    p.add_argument('--r2', required=True)
    p.add_argument('--out-r1', required=True)
    p.add_argument('--out-r2', required=True)
    p.add_argument('--metadata', required=True)
    p.add_argument('--scenario', choices=['clean', 'adapter', 'quality', 'combined'], required=True)
    p.add_argument('--seed', type=int, default=2026)
    p.add_argument('--max-pairs', type=int, default=600000)
    p.add_argument('--adapter-rate', type=float, default=.25)
    p.add_argument('--error-rate', type=float, default=.35)
    a = p.parse_args()
    info = generate(a.r1, a.r2, a.out_r1, a.out_r2, a.metadata,
                    a.scenario, a.seed, a.max_pairs, a.adapter_rate, a.error_rate)
    print(json.dumps(info, indent=2))
