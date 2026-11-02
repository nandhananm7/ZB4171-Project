#!/usr/bin/env python3
"""Aggregate the per-scenario AGORA feedback-ablation reports (benchmark only)."""
from __future__ import annotations
import argparse
import csv
import json
import os
from pathlib import Path
import re

DEFAULT_CASES = {"clean": "quality_trim", "adapter": "adapter_quality", "combined": "fastp_default"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=3101)
    parser.add_argument("--model", default=os.getenv("SOCLAAS_MODEL"))
    parser.add_argument("--include-quality", action="store_true", help="Also include quality:quality_trim if evaluated")
    args = parser.parse_args()
    if not args.model:
        parser.error("Set SOCLAAS_MODEL or use --model")
    repo = Path(__file__).resolve().parents[1]
    slug = re.sub(r"[^A-Za-z0-9_.-]", "_", args.model)
    base = repo / "results" / "evaluation" / "feedback_ablation" / f"seed_{args.seed}"
    cases = dict(DEFAULT_CASES)
    if args.include_quality:
        cases["quality"] = "quality_trim"
    rows = []
    for scenario, first in cases.items():
        report = base / scenario / first / slug / "summary.json"
        if not report.is_file():
            raise SystemExit(f"Missing evaluation: {report}\nRun agora_feedback_ablation.py evaluate for this case.")
        data = json.loads(report.read_text(encoding="utf-8"))
        if data["model"] != args.model or data["fixed_first_action"] != first or data["seed"] != args.seed:
            raise SystemExit(f"Incompatible report metadata: {report}")
        rows.append({
            "scenario": scenario,
            "first_action": first,
            "complete_pairs": data["complete_pairs"],
            "fully_benchmarked_pairs": data["fully_benchmarked_pairs"],
            "same_second_action_pairs": data["identical_second_action_pairs"],
            "no_feedback_actions": json.dumps(data["action_counts"]["no_feedback"], sort_keys=True),
            "feedback_actions": json.dumps(data["action_counts"]["feedback"], sort_keys=True),
            "median_nga50_delta_bp": data["median_paired_nga50_delta_bp"],
            "median_mismatch_delta": data["median_paired_mismatch_delta"],
            "missing_profiles": json.dumps(data["missing_second_action_profiles"]),
        })
    with (base / "FINAL_ABLATION_SUMMARY.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# AGORA — Milestone 9 feedback-ablation comparison", "",
             f"Seed: {args.seed}; SoCLaaS model: `{args.model}`.", "",
             "**Benchmark-only summary:** never provide this file or its reference metrics to the LLM.", "",
             "| Scenario | Fixed first action | Complete pairs | Fully evaluated | Identical second actions | Median Δ NGA50 (bp) | Median Δ mismatches/100 kbp |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for r in rows:
        dnga = r["median_nga50_delta_bp"]
        dmis = r["median_mismatch_delta"]
        lines.append(f"| {r['scenario']} | `{r['first_action']}` | {r['complete_pairs']} | {r['fully_benchmarked_pairs']} | {r['same_second_action_pairs']} | {'—' if dnga is None else f'{dnga:+,.0f}'} | {'—' if dmis is None else f'{dmis:+.2f}'} |")
    lines += ["", "Delta = feedback arm minus no-feedback arm, after replaying the frozen reference-free controller selection policy.",
              "Positive NGA50 and negative mismatch-rate delta favor feedback on the corresponding metric; they may conflict.",
              "The conditions share the same initial input, first repair and decision prompt; only the disclosed repair feedback differs.",
              "Calls are randomized/interleaved, but backend temperature/inference seeds are not controlled.",
              "Do not interpret these descriptive differences as statistical significance or organism-level generalization.", ""]
    (base / "FINAL_ABLATION_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print("Created:", base / "FINAL_ABLATION_SUMMARY.md")
    print("Created:", base / "FINAL_ABLATION_SUMMARY.csv")


if __name__ == "__main__":
    main()
