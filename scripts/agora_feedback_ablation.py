#!/usr/bin/env python3
"""AGORA Milestone 9: paired, controlled second-decision feedback ablation.

Run from the project root. No SPAdes runs, no benchmark inputs to model.
Identical model, baseline profile, first action and standard agent prompt in
both arms. Only first-trial result/guard feedback in the history differs.

run:      query SoCLaaS and persist resumable, paired decision records.
evaluate: retrospectively score decisions using existing profiles, and run
          reference-based QUAST separately on already-built FASTA assemblies.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import re
import statistics
import subprocess
import sys
import time

# Existing AGORA modules are supplied by the user's project.
from agora_controller import acceptable, load_profile, quality_score, summary
from agora_decide import ACTIONS, decide

SCENARIOS = ("clean", "adapter", "quality", "combined")
FIRST_ACTIONS = tuple(x for x in ACTIONS if x != "stop")
ARMS = ("no_feedback", "feedback")
REPORT_KEYS = ("NGA50", "Genome fraction (%)", "# misassemblies",
               "# mismatches per 100 kbp", "# indels per 100 kbp",
               "N50", "# contigs")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def workspace(root: Path, seed: int) -> Path:
    return root / "results" / "holdouts" / f"seed_{seed}"


def profile_file(work: Path, scenario: str, action: str) -> Path:
    return work / "results" / "challenges" / scenario / action / "profile.json"


def fasta_file(work: Path, scenario: str, action: str) -> Path:
    return work / "results" / "challenges" / scenario / action / "spades" / "contigs.fasta"


def output_dir(root: Path, seed: int, scenario: str, first: str, model: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9_.-]", "_", model)
    return (root / "results" / "evaluation" / "feedback_ablation" /
            f"seed_{seed}" / scenario / first / slug)


def history_for(first: str, candidate: dict, baseline: dict, arm: str) -> list[dict]:
    """Same action-history shape; only outcomes are masked in control arm."""
    if arm not in ARMS:
        raise ValueError("Invalid arm")
    passed, explanation = acceptable(baseline, candidate)
    return [{
        "action": first,
        "result": summary(candidate) if arm == "feedback" else None,
        "acceptable": passed if arm == "feedback" else None,
        "explanation": explanation if arm == "feedback" else None,
    }]


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    records = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSONL at {path}:{line_no}") from exc
            if not isinstance(record, dict):
                raise RuntimeError(f"Invalid record at {path}:{line_no}")
            records.append(record)
    return records


def successful_records(path: Path, count: int) -> dict[tuple[int, str], dict]:
    successful = {}
    for item in read_jsonl(path):
        key = (item.get("repetition"), item.get("arm"))
        if item.get("ok") and isinstance(key[0], int) and 1 <= key[0] <= count and key[1] in ARMS:
            if key in successful:
                # Multiple complete results for a slot make pair-wise analysis ambiguous.
                raise RuntimeError(f"Duplicate successful record {key}: {path}")
            successful[key] = item
    return successful


def order_for_repetition(repetition: int, order_seed: int) -> list[str]:
    arms = list(ARMS)
    random.Random(order_seed + repetition).shuffle(arms)
    return arms


def build_manifest(root: Path, base_file: Path, trial_file: Path,
                   scenario: str, first: str, seed: int, model: str, order_seed: int) -> dict:
    codefiles = ["agora_feedback_ablation.py", "agora_controller.py",
                 "agora_decide.py", "agora_profile.py", "soclaas_client.py"]
    scriptdir = root / "scripts"
    missing = [x for x in codefiles if not (scriptdir / x).is_file()]
    if missing:
        raise FileNotFoundError("Missing AGORA script(s): " + ", ".join(missing))
    return {
        "protocol": "agora-feedback-ablation-v1",
        "seed_bookkeeping_only": seed,
        "scenario_bookkeeping_only": scenario,
        "fixed_first_action": first,
        "model": model,
        "original_profile_sha256": sha256(base_file),
        "first_trial_profile_sha256": sha256(trial_file),
        "code_sha256": {name: sha256(scriptdir / name) for name in codefiles},
        "order_seed": order_seed,
        "prompt": "Unmodified agora_decide.llm_decide prompt for BOTH arms",
        "profile_input": "Original reference-free profile for BOTH arms",
        "history": "Same first action; feedback arm has numeric first-trial result/guard; control has nulls",
        "decoding": "AGORA SoCLaaS provider defaults (no explicit temperature or inference seed)",
        "model_does_not_receive": ["scenario label", "seed", "reference", "QUAST reference-based metrics"],
    }


def prepare_run(root: Path, seed: int, scenario: str, first: str, model: str,
                order_seed: int):
    work = workspace(root, seed)
    p_base = profile_file(work, scenario, "raw")
    p_trial = profile_file(work, scenario, first)
    if not p_base.is_file() or not p_trial.is_file():
        raise FileNotFoundError(
            "Missing existing first-trial QC profile. Required:\n" +
            str(p_base) + "\n" + str(p_trial) +
            "\nGenerate those Snakemake profiles in the held-out workspace first.")
    baseline = load_profile(p_base)
    trial = load_profile(p_trial)
    out = output_dir(root, seed, scenario, first, model)
    manifest = build_manifest(root, p_base, p_trial, scenario, first, seed, model, order_seed)
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing != manifest:
            raise RuntimeError("Experiment inputs/model/code changed. Restore the frozen inputs/code or archive this output directory before beginning a new experiment; refusing to mix decisions.")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return baseline, trial, out, manifest


def run_calls(root: Path, seed: int, scenario: str, first: str,
              model: str, count: int, order_seed: int) -> Path:
    baseline, trial, out, manifest = prepare_run(root, seed, scenario, first, model, order_seed)
    records_file = out / "decisions.jsonl"
    for rep in range(1, count + 1):
        for arm in order_for_repetition(rep, order_seed):
            existing = successful_records(records_file, count)
            if (rep, arm) in existing:
                print(f"[{rep}/{count}] {arm}: already done; skipping", flush=True)
                continue
            history = history_for(first, trial, baseline, arm)
            print(f"[{rep}/{count}] {arm}: asking for second decision...", flush=True)
            t0 = time.perf_counter()
            try:
                # CRITICAL: same original profile, prompt and baseline in both arms.
                # Post-repair QC is visible ONLY through the feedback-arm history.
                decision = decide("llm", baseline, history, model, summary(baseline))
                row = {"repetition": rep, "arm": arm, "ok": True,
                       "decision": decision, "latency_seconds": round(time.perf_counter() - t0, 3)}
                print(f"    diagnosis={decision['diagnosis']} second_action={decision['action']}", flush=True)
            except Exception as exc:
                row = {"repetition": rep, "arm": arm, "ok": False,
                       "latency_seconds": round(time.perf_counter() - t0, 3),
                       "error_type": type(exc).__name__, "error": str(exc)[:400]}
                print(f"    ERROR: {type(exc).__name__}: {str(exc)[:160]}", flush=True)
            with records_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
    successes = successful_records(records_file, count)
    for arm in ARMS:
        values = [r for (n, a), r in successes.items() if a == arm]
        actions = Counter(v["decision"]["action"] for v in values)
        print(f"{arm}: {len(values)}/{count} successful; actions={dict(actions)}")
    print("Saved:", out)
    return out


def replay_selection(baseline: dict, first_profile: dict, first: str,
                     second: str, second_profile: dict | None) -> dict:
    """Frozen reference-free controller policy for a fixed first + proposed second."""
    first_ok, first_reason = acceptable(baseline, first_profile)
    first_score = quality_score(baseline, first_profile) if first_ok else None
    winner = first if first_ok and first_score > 0 else "raw"
    winner_score = first_score if first_ok and first_score > 0 else 0.0
    result = {"selected": winner, "score": winner_score,
              "first_acceptable": first_ok, "first_explanation": first_reason,
              "second_acceptable": None, "second_explanation": None,
              "status": "evaluated"}
    if second == "stop":
        return result
    if second == first:
        result["status"] = "duplicate_action_violation"
        return result
    if second not in FIRST_ACTIONS:
        result["status"] = "invalid_action"
        return result
    if second_profile is None:
        result["status"] = "missing_second_action_profile"
        return result
    ok, explanation = acceptable(baseline, second_profile)
    result["second_acceptable"] = ok
    result["second_explanation"] = explanation
    if ok:
        score = quality_score(baseline, second_profile)
        if score > winner_score:
            result["score"] = score
            result["selected"] = second
    return result


def benchmark_quast(root: Path, seed: int, scenario: str, first: str, model: str,
                    reference: Path, threads: int, needed: set[str]) -> dict:
    """Separate benchmark operation. Never called by model-inference path."""
    work = workspace(root, seed)
    out = output_dir(root, seed, scenario, first, model)
    variants = {}
    for name in sorted(needed):
        candidate = fasta_file(work, scenario, name)
        if candidate.is_file() and candidate.stat().st_size:
            variants[name] = candidate
    if not variants:
        raise FileNotFoundError("No existing contigs.fasta assemblies found for independent QUAST evaluation")
    benchdir = out / "BENCHMARK_ONLY_QUAST"
    cmd = ["quast.py", *[str(p) for p in variants.values()], "-r", str(reference),
           "-l", ",".join(variants), "--threads", str(threads), "-o", str(benchdir)]
    print("Independent benchmark (NOT available to either arm):", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=root)
    with (benchdir / "report.tsv").open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        labels = next(reader)
        if labels[0] != "Assembly":
            raise ValueError("Unexpected QUAST report.tsv")
        metrics = {}
        for row in reader:
            if row and row[0] in REPORT_KEYS:
                metrics[row[0]] = dict(zip(labels[1:], row[1:]))
    return {"variants": list(variants), "metrics": metrics,
            "note": "BENCHMARK ONLY; never supplied to LLM", "reference_sha256": sha256(reference)}


def fmt_num(value, digits=2):
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def evaluate(root: Path, seed: int, scenario: str, first: str, model: str,
             count: int, order_seed: int, reference: Path, threads: int) -> Path:
    baseline, first_profile, out, _ = prepare_run(root, seed, scenario, first, model, order_seed)
    completed = successful_records(out / "decisions.jsonl", count)
    if not completed:
        raise RuntimeError("No successful LLM decisions; run the experiment first")
    needed = {"raw", first}
    for row in completed.values():
        action = row["decision"]["action"]
        if action in FIRST_ACTIONS:
            needed.add(action)
    profiles = {"raw": baseline, first: first_profile}
    for action in sorted(needed - set(profiles)):
        path = profile_file(workspace(root, seed), scenario, action)
        if path.is_file():
            profiles[action] = load_profile(path)
    missing_profiles = sorted(needed - set(profiles))
    if missing_profiles:
        print("WARNING: Some second-action profiles do not exist:", ", ".join(missing_profiles), flush=True)
    rows = []
    for (rep, arm), rec in sorted(completed.items()):
        second = rec["decision"]["action"]
        replay = replay_selection(baseline, first_profile, first, second, profiles.get(second))
        row = {"repetition": rep, "arm": arm, "first_action": first,
               "second_diagnosis": rec["decision"]["diagnosis"],
               "second_action": second, "final_selected_action": replay["selected"],
               "replay_status": replay["status"],
               "second_acceptable": replay["second_acceptable"],
               "first_acceptable": replay["first_acceptable"],
               "reference_free_score": replay["score"],
               "latency_seconds": rec["latency_seconds"]}
        rows.append(row)
    # QUAST runs only after inference and never leaks back to an agent.
    benchmark = benchmark_quast(root, seed, scenario, first, model, reference, threads,
                               needed | {r["final_selected_action"] for r in rows})
    metrics = benchmark["metrics"]
    for row in rows:
        selected = row["final_selected_action"]
        for metric in REPORT_KEYS:
            name = "bench_" + re.sub(r"[^A-Za-z0-9]+", "_", metric).strip("_").lower()
            rawval = metrics.get(metric, {}).get(selected)
            row[name] = float(rawval) if rawval not in (None, "-", "") else None
        if row["replay_status"] != "evaluated" or selected not in benchmark["variants"]:
            row["benchmark_status"] = "incomplete"
        else:
            row["benchmark_status"] = "evaluated"
    for name, group in (("paired_decisions.csv", rows),):
        with (out / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(group)
    (out / "BENCHMARK_ONLY_metrics.json").write_text(json.dumps(benchmark, indent=2) + "\n", encoding="utf-8")
    counts = {arm: Counter(r["second_action"] for r in rows if r["arm"] == arm) for arm in ARMS}
    valid_pairs = [(next(x for x in rows if x["repetition"] == rep and x["arm"] == "no_feedback"),
                    next(x for x in rows if x["repetition"] == rep and x["arm"] == "feedback"))
                   for rep in range(1, count + 1)
                   if (rep, "no_feedback") in completed and (rep, "feedback") in completed]
    paired_bench = [pair for pair in valid_pairs
                    if all(r["benchmark_status"] == "evaluated" for r in pair)]
    diff_nga = [(f["bench_nga50"] - c["bench_nga50"]) for c, f in paired_bench
                if f["bench_nga50"] is not None and c["bench_nga50"] is not None]
    diff_mismatches = [(f["bench_mismatches_per_100_kbp"] - c["bench_mismatches_per_100_kbp"])
                       for c, f in paired_bench
                       if f["bench_mismatches_per_100_kbp"] is not None and c["bench_mismatches_per_100_kbp"] is not None]
    report = {
        "protocol": "agora-feedback-ablation-v1",
        "seed": seed, "scenario": scenario, "fixed_first_action": first,
        "model": model, "requested_pairs": count,
        "complete_pairs": len(valid_pairs), "fully_benchmarked_pairs": len(paired_bench),
        "action_counts": {arm: dict(counts[arm]) for arm in ARMS},
        "identical_second_action_pairs": sum(c["second_action"] == f["second_action"] for c, f in valid_pairs),
        "paired_nga50_feedback_minus_control_bp": diff_nga,
        "median_paired_nga50_delta_bp": statistics.median(diff_nga) if diff_nga else None,
        "paired_mismatch_feedback_minus_control_per_100kbp": diff_mismatches,
        "median_paired_mismatch_delta": statistics.median(diff_mismatches) if diff_mismatches else None,
        "missing_second_action_profiles": missing_profiles,
        "notes": [
            "Descriptive paired inference calls; no random decoding seed or server-side deterministic guarantee.",
            "Both arms received ORIGINAL profile. The sole treatment difference is first-trial outcome history fields.",
            "First action is fixed; independent reference-based QUAST is run only after decisions are saved.",
            "Reference-free controller policy is replayed from existing assemblies; missing candidates are NOT executed or silently considered rejected.",
            "QUAST metrics reflect tradeoffs; do not declare a winner on NGA50 alone.",
        ],
    }
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = ["# AGORA — controlled feedback ablation", "",
             f"Seed: {seed}; scenario: {scenario}; fixed first action: `{first}`; model: `{model}`.", "",
             "Both groups saw the same original QC and identical decision prompt. Both were told that the same first action had been tried. Only the first-trial result and controller feedback were disclosed to the feedback group.", "",
             "| Group | Successful second decisions | Recommended second actions |",
             "|---|---:|---|"]
    for arm in ARMS:
        n = sum(r["arm"] == arm for r in rows)
        pairs = ", ".join(f"`{key}`: {value}" for key, value in sorted(counts[arm].items()))
        lines.append(f"| {arm} | {n} | {pairs or '—'} |")
    lines.extend(["", f"Complete matched pairs: **{len(valid_pairs)}/{count}**.",
                  f"Same recommended second action in **{report['identical_second_action_pairs']}** matched pairs.",
                  f"Paired benchmark comparisons available: **{len(paired_bench)}**.",
                  f"Median paired NGA50 feedback minus control: **{fmt_num(report['median_paired_nga50_delta_bp'], 0)} bp**.",
                  f"Median paired mismatch rate feedback minus control: **{fmt_num(report['median_paired_mismatch_delta'])} per 100 kbp**.",
                  "", "Positive NGA50 differences favor feedback on contiguity; negative mismatch differences favor feedback on sequence accuracy. Neither metric alone proves a better assembly.", "",
                  "## Caveats", "",
                  "- This tests whether providing feedback changes the **second decision**, not whether a fully autonomous system generalizes to other bacterial datasets.",
                  "- Replays the existing reference-free selection rule on precomputed assemblies; first/second actions are not cumulatively applied.",
                  "- If a recommended action's assembly is absent, its final outcome is **incomplete** and excluded from paired outcome comparisons.",
                  "- Repeated calls are correlated within a scenario; numerical medians are descriptive.",
                  "- Reference genome and QUAST benchmark metrics never enter the LLM decision calls.", ""])
    (out / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print("Saved:", out / "REPORT.md")
    print("Saved:", out / "paired_decisions.csv")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in ("run", "evaluate"):
        p = sub.add_parser(cmd)
        p.add_argument("--seed", type=int, default=3101)
        p.add_argument("--scenario", choices=SCENARIOS, required=True)
        p.add_argument("--first-action", choices=FIRST_ACTIONS, required=True)
        p.add_argument("--model", default=os.getenv("SOCLAAS_MODEL"))
        p.add_argument("--repetitions", type=int, default=10)
        p.add_argument("--order-seed", type=int, default=91)
        if cmd == "evaluate":
            p.add_argument("--reference", type=Path, required=True)
            p.add_argument("--threads", type=int, default=4)
    a = parser.parse_args(argv)
    if not a.model:
        parser.error("Set SOCLAAS_MODEL or pass --model")
    if not 1 <= a.repetitions <= 100:
        parser.error("--repetitions must be 1..100")
    if a.seed < 0 or a.order_seed < 0:
        parser.error("Seed values must be >= 0")
    if a.command == "evaluate" and (a.threads < 1 or not a.reference.is_file()):
        parser.error("Existing --reference FASTA and positive --threads are required")
    root = root_dir()
    if a.command == "run":
        run_calls(root, a.seed, a.scenario, a.first_action, a.model, a.repetitions, a.order_seed)
    else:
        evaluate(root, a.seed, a.scenario, a.first_action,
                 a.model, a.repetitions, a.order_seed, a.reference.resolve(), a.threads)


if __name__ == "__main__":
    main()
