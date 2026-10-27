#!/usr/bin/env python3
"""Summarize reference-free QUAST metrics for low-coverage experiment."""
import argparse
import json
from pathlib import Path
from summarize_quast import parse_quast


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--coverages", nargs="+", type=int, required=True)
    ap.add_argument("--reports", nargs="+", required=True)
    ap.add_argument("--metadata", nargs="+", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    if not (len(a.coverages) == len(a.reports) == len(a.metadata)):
        raise ValueError("coverage/report/metadata counts don't match")
    baseline = parse_quast(a.baseline)
    cases = {}
    for coverage, report, meta_path in zip(a.coverages, a.reports, a.metadata):
        metadata = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        if metadata["target_coverage_x"] != coverage:
            raise ValueError(f"Mismatched metadata for {coverage}x")
        qc = parse_quast(report)
        cases[str(coverage) + "x"] = {"qc": qc, "benchmark_metadata": metadata}
    summary = {
        "note": "Reference-free assembly metrics only; not recovery or correctness scores. Keep benchmark_metadata hidden from the LLM.",
        "full_preprocessed_baseline": baseline,
        "low_coverage_cases": cases
    }
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out}")

if __name__ == "__main__":
    main()
