#!/usr/bin/env python3
"""Create reproducible, pair-preserving low-coverage FASTQs with seqtk."""

import argparse
import gzip
from itertools import zip_longest
import json
import os
from pathlib import Path
import subprocess


def records(path):
    with gzip.open(path, "rt", encoding="ascii") as handle:
        while True:
            h = handle.readline()
            if not h:
                return
            s, plus, q = handle.readline(), handle.readline(), handle.readline()
            if not s or not plus or not q or not h.startswith("@") or not plus.startswith("+"):
                raise ValueError(f"Invalid/truncated FASTQ: {path}")
            seq = s.rstrip("\r\n")
            if len(seq) != len(q.rstrip("\r\n")):
                raise ValueError(f"Sequence and quality length differ: {path}")
            read_id = h.split()[0][1:].removesuffix("/1").removesuffix("/2")
            yield read_id, len(seq)


def sample_and_compress(src, dst, pairs, seed, threads):
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Explicitly use a matched seed AND matched integer count on each mate file.
    with dst.open("wb") as compressed_file:
        sampler = subprocess.Popen(
            ["seqtk", "sample", f"-s{seed}", str(src), str(pairs)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        try:
            compressor = subprocess.run(
                ["pigz", "-p", str(threads)], stdin=sampler.stdout,
                stdout=compressed_file, stderr=subprocess.PIPE, check=False
            )
        finally:
            sampler.stdout.close()
        stderr = sampler.stderr.read().decode("utf-8", errors="replace")
        status = sampler.wait()
        if status != 0 or compressor.returncode != 0:
            raise RuntimeError(
                f"Subsampling failed: seqtk={status}, pigz={compressor.returncode}; "
                f"seqtk stderr={stderr}; pigz stderr={compressor.stderr.decode(errors='replace')}"
            )


def verify_and_count(r1, r2, expected_pairs):
    n = total_bases = 0
    for a, b in zip_longest(records(r1), records(r2)):
        if a is None or b is None or a[0] != b[0]:
            raise ValueError(f"Read mates differ at pair {n+1}: {a} / {b}")
        n += 1
        total_bases += a[1] + b[1]
    if n != expected_pairs:
        raise ValueError(f"Expected {expected_pairs} pairs; got {n}")
    return n, total_bases


def main():
    ap = argparse.ArgumentParser()
    for name in ("r1", "r2", "fastp", "out_r1", "out_r2", "metadata"):
        ap.add_argument("--" + name.replace("_", "-"), required=True)
    ap.add_argument("--coverage", type=int, required=True)
    ap.add_argument("--genome-bp", type=int, required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--threads", type=int, default=2)
    a = ap.parse_args()

    with open(a.fastp, encoding="utf-8") as handle:
        stats = json.load(handle)["summary"]["after_filtering"]
    total_reads = int(stats["total_reads"])
    total_bases = int(stats["total_bases"])
    if total_reads <= 0 or total_reads % 2 != 0 or total_bases <= 0:
        raise ValueError("fastp summary doesn't contain a valid paired read population")
    available_pairs = total_reads // 2
    avg_pair_bp = total_bases / available_pairs
    pairs = round(a.coverage * a.genome_bp / avg_pair_bp)
    if pairs < 1 or pairs > available_pairs:
        raise ValueError(f"Cannot draw {pairs} pairs: only {available_pairs} exist")

    # Different fixed seed per coverage, but same exact seed for R1 and R2.
    seed = a.seed + a.coverage
    out1, out2, meta = map(Path, (a.out_r1, a.out_r2, a.metadata))
    part1, part2 = Path(str(out1) + ".partial"), Path(str(out2) + ".partial")
    print(f"Target {a.coverage}x: sampling {pairs:,} of {available_pairs:,} pairs (seed {seed})", flush=True)
    try:
        sample_and_compress(a.r1, part1, pairs, seed, a.threads)
        sample_and_compress(a.r2, part2, pairs, seed, a.threads)
        n, bases = verify_and_count(part1, part2, pairs)
        actual = bases / a.genome_bp
        os.replace(part1, out1)
        os.replace(part2, out2)
        result = {
            "scenario": "low_coverage",
            "target_coverage_x": a.coverage,
            "actual_nominal_coverage_x": round(actual, 4),
            "pairs": n,
            "total_bases": bases,
            "genome_bp": a.genome_bp,
            "seed": seed,
            "source": "fastp-preprocessed paired reads",
            "note": "Benchmark-only metadata: never provide scenario or injection label to the agent"
        }
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"Verified {n:,} paired reads; actual nominal coverage: {actual:.3f}x", flush=True)
    finally:
        for p in (part1, part2):
            if p.exists():
                p.unlink()

if __name__ == "__main__":
    main()
