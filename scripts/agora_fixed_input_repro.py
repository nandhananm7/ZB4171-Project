#!/usr/bin/env python3
"""AGORA fixed-input LLM initial-decision reproducibility audit.

Install in the project's scripts/ directory. Does NOT run an assembly, change
an agent's selection, or expose benchmark labels/reference metrics to the LLM.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import time

from agora_controller import load_profile, summary
from agora_decide import decide


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Malformed JSONL at {path}:{number}") from exc
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=3101)
    parser.add_argument("--scenario", choices=["clean", "adapter", "quality", "combined"], default="adapter")
    parser.add_argument("--repetitions", type=int, default=10, help="Total successful repetition slots to aim for")
    parser.add_argument("--model", default=os.environ.get("SOCLAAS_MODEL"))
    args = parser.parse_args()

    if not args.model:
        parser.error("Set SOCLAAS_MODEL or pass --model")
    if not 1 <= args.repetitions <= 100:
        parser.error("--repetitions must be between 1 and 100")

    root = Path.cwd()
    profile_path = (root / "results" / "holdouts" / f"seed_{args.seed}" /
                    "results" / "challenges" / args.scenario / "raw" / "profile.json")
    if not profile_path.is_file():
        parser.error(f"Raw reference-free QC profile missing: {profile_path}")

    # These match the controller's FIRST call precisely: baseline profile,
    # empty repair history, and the summary of that same baseline profile.
    profile = load_profile(profile_path)
    baseline_observation = summary(profile)
    safe_model_name = re.sub(r"[^A-Za-z0-9_.-]", "_", args.model)
    outdir = root / "results" / "evaluation" / "fixed_input_repro" / f"seed_{args.seed}" / args.scenario / safe_model_name
    outdir.mkdir(parents=True, exist_ok=True)
    manifest_path = outdir / "manifest.json"
    results_path = outdir / "decisions.jsonl"
    report_path = outdir / "summary.json"

    code_files = ["agora_controller.py", "agora_decide.py", "soclaas_client.py", "agora_profile.py"]
    manifest = {
        "protocol": "fixed-first-decision-v1",
        "model": args.model,
        "profile_sha256": sha256_file(profile_path),
        "code_sha256": {f: sha256_file(root / "scripts" / f) for f in code_files},
        "history": [],
        "decoding_configuration": "Provider defaults: no temperature or seed specified by AGORA client",
        "note": "Scenario name is local bookkeeping only; not passed to LLM. No reference metrics used.",
    }
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous != manifest:
            raise SystemExit("ERROR: Model/profile/code changed since this audit started. Use a fresh run or archive the old directory first.")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    records = read_jsonl(results_path)
    completed = {r["repetition"] for r in records if r.get("ok")}
    for i in range(1, args.repetitions + 1):
        if i in completed:
            print(f"[{i}/{args.repetitions}] already complete; skipping", flush=True)
            continue
        print(f"[{i}/{args.repetitions}] requesting one independent initial LLM decision...", flush=True)
        started = time.perf_counter()
        try:
            decision = decide("llm", profile, [], args.model, baseline_observation)
            record = {"repetition": i, "ok": True, "latency_seconds": round(time.perf_counter()-started, 3),
                      "decision": decision}
            completed.add(i)
            print(f"    diagnosis={decision['diagnosis']} action={decision['action']}", flush=True)
        except Exception as exc:
            record = {"repetition": i, "ok": False, "latency_seconds": round(time.perf_counter()-started, 3),
                      "error_type": type(exc).__name__, "error": str(exc)[:500]}
            print(f"    ERROR: {type(exc).__name__}: {str(exc)[:200]}", flush=True)
        with results_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()

    successful = {r["repetition"]: r for r in read_jsonl(results_path)
                  if r.get("ok") and r["repetition"] <= args.repetitions}
    ordered = [successful[i] for i in sorted(successful)]
    actions = Counter(r["decision"]["action"] for r in ordered)
    diagnoses = Counter(r["decision"]["diagnosis"] for r in ordered)
    report = {"requested_repetitions": args.repetitions, "successful_repetitions": len(ordered),
              "action_counts": dict(actions), "diagnosis_counts": dict(diagnoses),
              "modal_action_fraction": round(max(actions.values())/len(ordered), 3) if ordered else None,
              "latency_seconds": [r["latency_seconds"] for r in ordered],
              "notes": "Descriptive consistency only; no temperature/seed control, no assembly evaluation."}
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("\nSummary:", json.dumps(report, indent=2))
    print("\nSaved:", outdir)


if __name__ == "__main__":
    main()
