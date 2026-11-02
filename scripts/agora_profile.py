#!/usr/bin/env python3
"""Reference-free, strictly whitelisted QC observations for challenge agents."""
import argparse
import json
import math
from itertools import zip_longest
from pathlib import Path

# Reuse the tested QUAST reader and paired FASTQ iterator already in AGORA.
from agora_base_qc import read_quast, fastq_records

ADAPTER_MOTIF = 'AGATCGGA'  # public Illumina adapter motif; NOT an injected label


def profile(r1, r2, quast, genome_prior=4600000):
    if genome_prior <= 0:
        raise ValueError('Genome-size prior must be positive')
    pairs = bases = good20 = good30 = gc = n_bases = tail_n = tail_bad = hits = reads = 0
    for left, right in zip_longest(fastq_records(r1), fastq_records(r2)):
        if left is None or right is None or left[0] != right[0]:
            raise ValueError('FASTQ pairs are not synchronized')
        pairs += 1
        for _, seq, qual in (left, right):
            reads += 1
            bases += len(seq)
            gc += seq.count('G') + seq.count('C')
            n_bases += seq.count('N')
            hits += int(ADAPTER_MOTIF in seq[-35:])
            for ch in qual:
                q = ord(ch) - 33
                if not 0 <= q <= 93:
                    raise ValueError('Invalid Phred+33 quality')
                good20 += q >= 20
                good30 += q >= 30
            for ch in qual[-20:]:
                tail_n += 1
                tail_bad += ord(ch) - 33 < 20
    if not pairs or not bases or not tail_n:
        raise ValueError('No valid paired FASTQ records')
    data = {
        'schema_version': 'agora.challenge.v1',
        'read_qc': {
            'read_pairs': pairs,
            'total_bases': bases,
            'mean_read_length_bp': round(bases / (2 * pairs), 3),
            'q20_percent': round(good20 / bases * 100, 3),
            'q30_percent': round(good30 / bases * 100, 3),
            'gc_percent': round(gc / bases * 100, 3),
            'n_percent': round(n_bases / bases * 100, 4),
        },
        'assembly_qc': read_quast(quast),
        'coverage_estimate': {
            'estimated_x': round(bases / genome_prior, 3),
            'expected_genome_size_prior_bp': genome_prior,
        },
        'artifact_signals': {
            'adapter_motif_end_percent': round(hits / reads * 100, 3),
            'tail_bases_below_q20_percent': round(tail_bad / tail_n * 100, 3),
            'qualification': 'Heuristics from read sequences and Phred scores, not definitive diagnosis',
        },
    }
    validate_profile(data)
    return data


SCHEMA = {
    'read_qc': {'read_pairs', 'total_bases', 'mean_read_length_bp', 'q20_percent',
                'q30_percent', 'gc_percent', 'n_percent'},
    'assembly_qc': {'contig_count', 'largest_contig_bp', 'assembly_length_bp',
                    'gc_percent', 'n50_bp', 'l50'},
    'coverage_estimate': {'estimated_x', 'expected_genome_size_prior_bp'},
    'artifact_signals': {'adapter_motif_end_percent', 'tail_bases_below_q20_percent',
                         'qualification'},
}


def validate_profile(p):
    if not isinstance(p, dict) or set(p) != {'schema_version', *SCHEMA}:
        raise ValueError('Unexpected top-level fields; possible label/reference leakage')
    if p['schema_version'] != 'agora.challenge.v1':
        raise ValueError('Unexpected profile version')
    for section, keys in SCHEMA.items():
        value = p[section]
        if not isinstance(value, dict) or set(value) != keys:
            raise ValueError(f'Unapproved keys or missing data in {section}')
        for k, v in value.items():
            if k == 'qualification':
                if not isinstance(v, str) or len(v) > 250:
                    raise ValueError('Invalid qualification')
            elif isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ValueError(f'Invalid number {section}.{k}')
            elif v < 0:
                raise ValueError(f'Negative number {section}.{k}')
    for section, keys in (('read_qc', ('q20_percent','q30_percent','gc_percent','n_percent')),
                          ('assembly_qc', ('gc_percent',)),
                          ('artifact_signals', ('adapter_motif_end_percent','tail_bases_below_q20_percent'))):
        for k in keys:
            if not 0 <= p[section][k] <= 100:
                raise ValueError(f'Invalid percentage: {section}.{k}')
    if p['assembly_qc']['n50_bp'] <= 0 or p['read_qc']['read_pairs'] <= 0:
        raise ValueError('Empty assembly or reads')
    return p


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--r1', required=True)
    a.add_argument('--r2', required=True)
    a.add_argument('--quast', required=True)
    a.add_argument('--genome-prior', type=int, default=4600000)
    a.add_argument('--output', required=True)
    args = a.parse_args()
    result = profile(args.r1, args.r2, args.quast, args.genome_prior)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_suffix('.partial')
    part.write_text(json.dumps(result, indent=2)+'\n', encoding='utf8')
    part.replace(out)
    print('Agent-safe profile written:', out)


if __name__ == '__main__':
    main()
