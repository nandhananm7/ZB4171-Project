#!/usr/bin/env python3
"""Print a reference-free comparison of default and repair-action QUAST reports.

This is an exploratory diagnostic, NOT assembly correctness or recovery scoring.
"""
import argparse
from pathlib import Path


def parse_quast(path):
    metrics = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines()[1:]:
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        metric, value = fields[0].strip(), fields[1].strip()
        if metric in {"# contigs", "Largest contig", "Total length", "N50", "L50", "GC (%)"}:
            metrics[metric] = float(value) if metric == "GC (%)" else int(value.replace(",", ""))
    required = {"# contigs", "Largest contig", "Total length", "N50", "L50", "GC (%)"}
    missing = required.difference(metrics)
    if missing:
        raise ValueError(f"Missing metrics in {path}: {sorted(missing)}")
    return metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", type=int, choices=[8, 15, 30], required=True)
    ap.add_argument("--strategy", choices=["short_k", "auto_cutoff"], required=True)
    args = ap.parse_args()
    old = parse_quast(f"results/lowcov/{args.coverage}x/quast/report.tsv")
    new = parse_quast(f"results/repair/{args.coverage}x/{args.strategy}/quast/report.tsv")
    print(f"AGORA {args.coverage}x: default vs {args.strategy} (reference-free only)")
    print(f"{'Metric':<22} {'Default':>14} {'Action':>14} {'Delta':>14}")
    for metric in ("# contigs", "N50", "Largest contig", "Total length", "L50", "GC (%)"):
        fmt = ",.2f" if metric == "GC (%)" else ",d"
        a, b = old[metric], new[metric]
        delta = b - a
        print(f"{metric:<22} {format(a, fmt):>14} {format(b, fmt):>14} {delta:>+14,.2f}" if metric == "GC (%)" else
              f"{metric:<22} {a:>14,d} {b:>14,d} {delta:>+14,d}")
    pct_n50 = (new['N50'] / old['N50'] - 1) * 100
    print(f"N50 change: {pct_n50:+.2f}%")
    print("Caution: A higher N50 does not establish greater correctness.")


if __name__ == "__main__":
    main()
