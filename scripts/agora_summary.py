#!/usr/bin/env python3
"""AGORA benchmark-only cross-scenario evaluation.

Reads completed reference-based QUAST comparison.json and controller decision logs.
NEVER import or call from an agent, QC profiler, or repair controller.
No dependency outside the Python standard library; never runs Snakemake or an LLM.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

SCENARIOS = ("clean", "adapter", "quality", "combined")
STRATEGIES = ("raw", "fastp_default", "rule_zero", "rule_iterative",
              "llm_zero", "llm_iterative", "clean_control")
AGENTS = ("rule_zero", "rule_iterative", "llm_zero", "llm_iterative")
# This is benchmark ground truth; NEVER send it to a decision-making agent.
TRUTH = {
    "clean": "no_strong_signal",
    "adapter": "adapter_signal",
    "quality": "quality_signal",
    "combined": "mixed_signal",
}
METRICS = {
    "# contigs": "contigs",
    "N50": "n50_bp",
    "NGA50": "nga50_bp",
    "Genome fraction (%)": "genome_fraction_percent",
    "# misassemblies": "misassemblies",
    "# mismatches per 100 kbp": "mismatches_per_100kb",
    "# indels per 100 kbp": "indels_per_100kb",
}
FIELDNAMES = (
    "scenario", "strategy", "selected_action", "first_diagnosis", "expected_diagnosis",
    "diagnosis_category_match", "first_action", "decision_actions", "repair_attempts",
    "accepted_attempts", "model", *METRICS.values(),
    "nga50_change_vs_fastp_percent", "mismatch_change_vs_fastp_per_100kb",
)
DECISION_FIELDS = ("scenario", "strategy", "first_diagnosis", "expected_diagnosis",
                   "diagnosis_category_match", "first_action", "decision_actions",
                   "selected_action", "repair_attempts", "accepted_attempts", "model",
                   "first_reasoning")


def number(value):
    """Parse QUAST metric or return None for missing/unreported measurements."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(str(value).strip().replace(",", ""))
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def md(value, decimals=2):
    if value is None or value == "":
        return "—"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:,.{decimals}f}" if isinstance(value, float) else f"{value:,}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def calculate(root: Path):
    rows, agent_rows, warnings = [], [], []
    for scenario in SCENARIOS:
        path = root / "results/evaluation/challenges" / scenario / "comparison.json"
        if not path.exists():
            warnings.append(f"Missing reference evaluation for {scenario}: {path.relative_to(root)}")
            continue
        comp = load_json(path)
        metrics = comp.get("metrics", {})
        strategies = comp.get("strategies", [])
        if not isinstance(strategies, list) or not isinstance(metrics, dict):
            warnings.append(f"Malformed comparison JSON: {path}")
            continue
        unexpected = set(strategies) - set(STRATEGIES)
        if unexpected:
            warnings.append(f"Unknown strategy labels in {scenario}: {sorted(unexpected)}")
        missing_metrics = set(METRICS) - set(metrics)
        if missing_metrics:
            warnings.append(f"Missing QUAST metrics in {scenario}: {sorted(missing_metrics)}")
        standard_n = number(metrics.get("NGA50", {}).get("fastp_default"))
        standard_m = number(metrics.get("# mismatches per 100 kbp", {}).get("fastp_default"))
        for strategy in STRATEGIES:
            if strategy not in strategies:
                if strategy != "clean_control":
                    warnings.append(f"{scenario}: evaluation missing strategy {strategy}")
                continue
            extracted = {
                name: number(metrics.get(key, {}).get(strategy))
                for key, name in METRICS.items()
            }
            # Distinguish genuinely missing values from a numeric zero.
            row = {
                "scenario": scenario, "strategy": strategy,
                "selected_action": ("clean/raw" if strategy == "clean_control" else strategy),
                "first_diagnosis": "", "expected_diagnosis": TRUTH[scenario],
                "diagnosis_category_match": "", "first_action": "", "decision_actions": "",
                "repair_attempts": "", "accepted_attempts": "", "model": "",
                **extracted, "nga50_change_vs_fastp_percent": None,
                "mismatch_change_vs_fastp_per_100kb": None,
            }
            if strategy in AGENTS:
                audit_path = root / "results/agent_runs" / scenario / f"{strategy}.json"
                if not audit_path.is_file():
                    warnings.append(f"{scenario}: missing agent log {audit_path.relative_to(root)}")
                else:
                    if audit_path.stat().st_mtime > path.stat().st_mtime + 2:
                        warnings.append(
                            f"STALE {scenario}/{strategy}: agent log newer than comparison.json. "
                            "Rerun agora_evaluate.py for this scenario."
                        )
                    audit = load_json(audit_path)
                    decisions = audit.get("decisions") or []
                    attempts = audit.get("attempts") or []
                    first = decisions[0] if decisions else {}
                    actual = first.get("diagnosis", "")
                    chosen = audit.get("selected_action", "")
                    if chosen and chosen not in ("raw", "fastp_default", "explicit_adapter",
                                               "quality_trim", "adapter_quality"):
                        warnings.append(f"{scenario}/{strategy}: unknown selected action {chosen}")
                    row.update({
                        "selected_action": chosen,
                        "first_diagnosis": actual,
                        "diagnosis_category_match": ("yes" if actual == TRUTH[scenario] else "no") if actual else "",
                        "first_action": first.get("action", ""),
                        "decision_actions": ";".join(str(d.get("action", "")) for d in decisions),
                        "repair_attempts": len(attempts),
                        "accepted_attempts": sum(bool(a.get("acceptable")) for a in attempts),
                        "model": audit.get("model") or "",
                    })
                    agent_rows.append({key: row.get(key, "") for key in DECISION_FIELDS} |
                                      {"first_reasoning": first.get("reasoning", "")})
            if strategy != "clean_control":
                q = extracted["nga50_bp"]
                m = extracted["mismatches_per_100kb"]
                if standard_n and q is not None:
                    row["nga50_change_vs_fastp_percent"] = round(100 * (q / standard_n - 1), 3)
                if standard_m is not None and m is not None:
                    row["mismatch_change_vs_fastp_per_100kb"] = round(m - standard_m, 3)
            rows.append(row)
    return rows, agent_rows, warnings


def write_csv(path: Path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def create_report(rows, agent_rows, warnings):
    lines = [
        "# AGORA — Cross-scenario experimental summary", "",
        "**Benchmark-only report.** Reference-based QUAST metrics and injected-failure labels "
        "must never be passed into either agent's prompt or controller feedback.", "",
        "## Experiment design", "",
        "The evaluation compares raw assembly, standard fastp, rule-based zero-shot/iterative "
        "and LLM zero-shot/iterative pipelines on clean, adapter-only, quality-only, and "
        "combined-corruption cases. These are descriptive results from the available runs; "
        "they are not evidence of statistical significance.", "",
    ]
    for scenario in SCENARIOS:
        subset = [r for r in rows if r["scenario"] == scenario]
        lines.extend([f"## {scenario.replace('_', ' ').title()} scenario", ""])
        if not subset:
            lines.extend(["No evaluation file found for this scenario.", ""])
            continue
        lines.extend([
            "| Strategy | First diagnosis | Decision actions | Selected | Trials | NGA50 (bp) | Genome fraction (%) | Misassemblies | Mismatches / 100 kbp |",
            "|---|---|---|---|---:|---:|---:|---:|---:|",
        ])
        for r in subset:
            lines.append("| " + " | ".join([
                md(r["strategy"]), md(r["first_diagnosis"]),
                md(r["decision_actions"].replace(";", " → ")), md(r["selected_action"]),
                md(r["repair_attempts"]), md(r["nga50_bp"], 0),
                md(r["genome_fraction_percent"], 3), md(r["misassemblies"], 0),
                md(r["mismatches_per_100kb"]),
            ]) + " |")
        lines.extend(["", "The CSV contains N50, contig count, indels, and changes relative to the standard fastp comparator.", ""])
    lines.extend([
        "## Initial diagnosis-category agreement", "",
        "This is an **exploratory exact-category check** against the injected scenario "
        "(clean → no_strong_signal; adapter → adapter_signal; quality → quality_signal; "
        "combined → mixed_signal). It is *not* an independent estimate of biological "
        "diagnostic accuracy or evidence that stronger preprocessing is the correct repair.", "",
        "| Agent | Exact categories matched | Evaluated scenarios |", "|---|---:|---:|",
    ])
    for strategy in AGENTS:
        subset = [r for r in agent_rows if r["strategy"] == strategy and r["first_diagnosis"]]
        wins = sum(r["diagnosis_category_match"] == "yes" for r in subset)
        lines.append(f"| {strategy} | {wins} | {len(subset)} |")
    lines.extend([
        "", "## Interpretation notes", "",
        "- A controller-accepted trial is a **reference-free heuristic pass**, not proof of improved assembly correctness.",
        "- NGA50, genome fraction, misassemblies and mismatch/indel rates reflect different "
        "quality objectives. Avoid combining them into an unregistered post-hoc single 'winner'.",
        "- An agent's first action and its final selected assembly must be reported separately.",
        "- The clean-control assembly is not guaranteed to be the maximum for every metric.",
        "- Review differences in repair attempts, CPU time, and API latency separately if logs provide them.",
        "- Freeze prompts/rules and use unseen injection seeds before generalizing from these scenarios.",
        "", "## Data checks", "",
    ])
    if warnings:
        lines.extend(f"- {w}" for w in warnings)
    else:
        lines.append("- No missing or stale inputs detected by basic file checks.")
    lines.append("")
    return "\n".join(lines)


def generate(root: Path, outdir: Path):
    root = root.resolve()
    outdir = outdir.resolve()
    rows, agent_rows, warnings = calculate(root)
    outdir.mkdir(parents=True, exist_ok=True)
    csvpath = outdir / "agora_comparison.csv"
    agentpath = outdir / "agent_decisions.csv"
    mdpath = outdir / "AGORA_Cross_Scenario_Report.md"
    write_csv(csvpath, FIELDNAMES, rows)
    write_csv(agentpath, DECISION_FIELDS, agent_rows)
    mdpath.write_text(create_report(rows, agent_rows, warnings), encoding="utf-8")
    for p in (csvpath, agentpath, mdpath):
        print("Saved:", p)
    for warning in warnings:
        print("WARNING:", warning)
    print(f"Processed {len(set(r['scenario'] for r in rows))}/4 scenarios and "
          f"{len(agent_rows)} agent logs.")
    return rows, warnings


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    project = args.project_root.resolve()
    output = args.output_dir.resolve() if args.output_dir else project / "results/evaluation/summary"
    generate(project, output)
