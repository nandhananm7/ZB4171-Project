#!/usr/bin/env python3
"""Build an agent-safe reference-free QC profile from paired reads and QUAST.

Intentionally does NOT open benchmark metadata, reference FASTA, or reference
QUAST reports. Only an explicit whitelist of metrics is serialized.
"""

import argparse
import csv
import gzip
import json
from itertools import zip_longest
from pathlib import Path


ALLOWED_QUAST_FIELDS = {
    "# contigs": "contig_count",
    "Largest contig": "largest_contig_bp",
    "Total length": "assembly_length_bp",
    "N50": "n50_bp",
    "L50": "l50",
    "GC (%)": "gc_percent",
}


def read_quast(path):
    """Parse one-assembly reference-free QUAST TSV using a strict whitelist."""
    values = {}
    with open(path, newline="", encoding="utf-8") as stream:
        reader = csv.reader(stream, delimiter="\t")
        header = next(reader, [])
        if len(header) != 2 or header[0] != "Assembly":
            raise ValueError("Expected a single-assembly QUAST report.tsv")
        for row in reader:
            if len(row) == 2 and row[0] in ALLOWED_QUAST_FIELDS:
                metric = ALLOWED_QUAST_FIELDS[row[0]]
                if metric in values:
                    raise ValueError(f"Duplicate QUAST metric: {row[0]}")
                values[metric] = (float(row[1]) if metric == "gc_percent"
                                  else int(row[1].replace(",", "")))
    missing = set(ALLOWED_QUAST_FIELDS.values()) - set(values)
    if missing:
        raise ValueError(f"QUAST report missing required metrics: {sorted(missing)}")
    return values


def fastq_records(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="ascii") as handle:
        while True:
            header = handle.readline()
            if not header:
                break
            seq = handle.readline()
            plus = handle.readline()
            qual = handle.readline()
            if not (seq and plus and qual and header.startswith("@")
                    and plus.startswith("+")):
                raise ValueError("Malformed or truncated FASTQ input")
            seq = seq.rstrip("\r\n").upper()
            qual = qual.rstrip("\r\n")
            if len(seq) != len(qual):
                raise ValueError("FASTQ sequence/quality length mismatch")
            name = header[1:].split()[0].removesuffix("/1").removesuffix("/2")
            yield name, seq, qual


def read_pair_stats(r1, r2):
    pairs = bases = gc = ns = q20 = q30 = 0
    for left, right in zip_longest(fastq_records(r1), fastq_records(r2)):
        if left is None or right is None:
            raise ValueError("R1 and R2 have different numbers of reads")
        if left[0] != right[0]:
            raise ValueError(f"Paired FASTQ read names do not match at pair {pairs + 1}")
        pairs += 1
        for _, seq, qual in (left, right):
            bases += len(seq)
            gc += seq.count("G") + seq.count("C")
            ns += seq.count("N")
            for c in qual:
                phred = ord(c) - 33
                if not 0 <= phred <= 93:
                    raise ValueError("Invalid Phred+33 FASTQ quality value")
                q20 += phred >= 20
                q30 += phred >= 30
    if pairs == 0 or bases == 0:
        raise ValueError("No sequencing reads found")
    return {
        "read_pairs": pairs,
        "total_bases": bases,
        "mean_read_length_bp": round(bases / (2 * pairs), 3),
        "q20_percent": round(100 * q20 / bases, 3),
        "q30_percent": round(100 * q30 / bases, 3),
        "gc_percent": round(100 * gc / bases, 3),
        "n_percent": round(100 * ns / bases, 4),
    }


def build_profile(r1, r2, quast_path, expected_genome_size_bp):
    if expected_genome_size_bp <= 0:
        raise ValueError("Expected approximate genome size must be positive")
    reads = read_pair_stats(r1, r2)
    assembly = read_quast(quast_path)
    return {
        "schema_version": "1.0",
        "read_qc": reads,
        "assembly_qc": assembly,
        "coverage_estimate": {
            "estimated_x": round(reads["total_bases"] / expected_genome_size_bp, 3),
            "method": "sequenced_bases / approximate_expected_genome_size",
            "expected_genome_size_prior_bp": expected_genome_size_bp,
            "qualification": (
                "Approximate nominal depth, not measured depth; assumes most reads "
                "come from the target genome and depends on a species-size prior."
            ),
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--r1", required=True)
    ap.add_argument("--r2", required=True)
    ap.add_argument("--quast", required=True)
    ap.add_argument("--expected-genome-size-bp", type=int, required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    profile = build_profile(args.r1, args.r2, args.quast,
                            args.expected_genome_size_bp)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement prevents a partial JSON profile from being consumed.
    partial = destination.with_suffix(destination.suffix + ".partial")
    try:
        partial.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)
    print(f"Wrote agent-safe profile: {destination}")


if __name__ == "__main__":
    main()
