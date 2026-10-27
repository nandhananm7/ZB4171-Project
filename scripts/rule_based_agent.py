#!/usr/bin/env python3
"""AGORA v0 rule-based diagnostic baseline: reference-free, low coverage only.

This intentionally does NOT use known failure labels, reference alignments,
previous benchmark results, or the folder name to make a prediction.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

ALLOWED_TOP_LEVEL = {"schema_version", "read_qc", "assembly_qc", "coverage_estimate"}
RESTRICTED_FIELDS = {
    "benchmark_metadata", "scenario", "target_coverage_x",
    "actual_nominal_coverage_x", "genome_fraction", "nga50",
    "misassemblies", "reference_length", "reference_fasta", "injected_label",
}


def find_restricted(obj, prefix=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            label = f"{prefix}.{key}" if prefix else key
            if key.lower() in RESTRICTED_FIELDS:
                raise ValueError(f"Restricted benchmark/reference field in profile: {label}")
            find_restricted(value, label)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            find_restricted(value, f"{prefix}[{index}]")


def require_number(mapping, field, *, positive=False):
    value = mapping.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Missing or nonnumeric field: {field}")
    value = float(value)
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f"Invalid numeric value for {field}: {value}")
    return value


def diagnose(profile):
    if not isinstance(profile, dict):
        raise ValueError("Profile must be a JSON object")
    find_restricted(profile)
    extra = set(profile) - ALLOWED_TOP_LEVEL
    if extra:
        raise ValueError(f"Unexpected top-level fields in agent profile: {sorted(extra)}")
    for section in ("read_qc", "assembly_qc", "coverage_estimate"):
        if not isinstance(profile.get(section), dict):
            raise ValueError(f"Missing {section} section")

    read = profile["read_qc"]
    asm = profile["assembly_qc"]
    cov = profile["coverage_estimate"]
    coverage = require_number(cov, "estimated_x", positive=True)
    n50 = require_number(asm, "n50_bp", positive=True)
    contigs = require_number(asm, "contig_count", positive=True)
    q30 = require_number(read, "q30_percent")
    if not 0 <= q30 <= 100:
        raise ValueError("Q30 percentage must be in [0, 100]")

    # These diagnostic thresholds are starting heuristics, NOT fitted estimates
    # of assembly quality or a learned biological model. Freeze them before
    # evaluating on independently generated datasets.
    if coverage < 10:
        diagnosis = "suspected_low_coverage"
        severity = "severe"
    elif coverage < 20:
        diagnosis = "suspected_low_coverage"
        severity = "moderate"
    else:
        diagnosis = "no_strong_low_coverage_signal"
        severity = "not_assigned"

    evidence = [
        f"Estimated nominal coverage: {coverage:.2f}x (genome-size-prior dependent)",
        f"Assembly contiguity: N50={n50:,.0f} bp; contigs={contigs:,.0f}",
        f"Q30 base fraction: {q30:.2f}% (cannot independently rule out other read problems)",
    ]
    if diagnosis == "suspected_low_coverage":
        explanation = (
            "Sequencing depth appears limited relative to a typical bacterial "
            "short-read assembly. Fragmentation may be related, but the profile "
            "does not prove a unique cause."
        )
        action_reason = (
            "A no-change control is the conservative first recommendation: "
            "assembly parameters cannot restore genomic information absent from "
            "the reads. Additional sequencing would be an external intervention."
        )
    else:
        explanation = (
            "The coverage estimate alone does not indicate a severe or moderate "
            "depth shortfall. This does NOT rule out adapters, contamination, or errors."
        )
        action_reason = (
            "No low-coverage-specific repair is justified by this preliminary "
            "rule set. Other diagnoses are not implemented in v0."
        )

    return {
        "decision_schema_version": "0.1",
        "diagnosis": diagnosis,
        "severity": severity,
        "evidence": evidence,
        "reasoning": explanation,
        "action": {"name": "no_change", "parameters": {}},
        "action_reasoning": action_reason,
        "limitations": [
            "Only low coverage is diagnosed by this v0 rule-based baseline.",
            "Coverage estimate is approximate and can be biased by contamination or the genome-size prior.",
            "No reference-based metrics or benchmark labels were used.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    decision = diagnose(profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
    print(f"Saved diagnostic decision to {args.output}")
    print(f"Diagnosis: {decision['diagnosis']} ({decision['severity']})")
    print(f"Action: {decision['action']['name']}")


if __name__ == "__main__":
    main()
