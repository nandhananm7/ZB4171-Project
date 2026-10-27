#!/usr/bin/env python3
"""Verify FASTQ pairing and basic record formatting without extra packages."""

import argparse
import gzip
from itertools import zip_longest
from pathlib import Path


def read_records(file):
    opener = gzip.open if str(file).endswith(".gz") else open
    with opener(file, "rt", encoding="ascii") as f:
        while True:
            header = f.readline()
            if not header:
                return
            sequence, plus, quality = f.readline(), f.readline(), f.readline()
            if not sequence or not plus or not quality:
                raise ValueError(f"Truncated FASTQ: {file}")
            if not header.startswith("@") or not plus.startswith("+"):
                raise ValueError(f"Malformed FASTQ: {file}")
            if len(sequence.rstrip("\r\n")) != len(quality.rstrip("\r\n")):
                raise ValueError(f"Sequence/quality mismatch: {file}")
            name = header.split()[0].removeprefix("@").removesuffix("/1").removesuffix("/2")
            yield name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("r1")
    ap.add_argument("r2")
    ap.add_argument("--max-pairs", type=int, default=20000, help="0 means check entire file")
    args = ap.parse_args()
    checked = 0
    for name1, name2 in zip_longest(read_records(args.r1), read_records(args.r2)):
        if name1 != name2 or name1 is None:
            raise ValueError(f"Pair mismatch at index {checked}: {name1} vs {name2}")
        checked += 1
        if args.max_pairs and checked >= args.max_pairs:
            break
    if not checked:
        raise ValueError("No records found")
    print(f"Verified {checked:,} matching paired FASTQ records")


if __name__ == "__main__":
    main()
