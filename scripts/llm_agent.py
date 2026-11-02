#!/usr/bin/env python3
"""AGORA: reference-free, diagnosis-only LLM prototype.

Reads an existing agent-safe profile. The model never executes shell commands;
the returned action is a proposal, validated against a fixed whitelist.
Requires: pip install openai 'pydantic>=2'
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# An explicit nested allowlist prevents benchmark labels and reference metrics
# from being forwarded accidentally as profiles evolve.
ALLOWED_KEYS = {
    "": {"schema_version", "read_qc", "assembly_qc", "coverage_estimate"},
    "read_qc": {"read_pairs", "total_bases", "mean_read_length_bp", "q20_percent", "q30_percent", "gc_percent", "n_percent"},
    "assembly_qc": {"contig_count", "largest_contig_bp", "assembly_length_bp", "gc_percent", "n50_bp", "l50"},
    "coverage_estimate": {"estimated_x", "method", "expected_genome_size_prior_bp", "qualification"},
}
NUMERIC_FIELDS = {
    "read_qc": {"read_pairs", "total_bases", "mean_read_length_bp", "q20_percent", "q30_percent", "gc_percent", "n_percent"},
    "assembly_qc": {"contig_count", "largest_contig_bp", "assembly_length_bp", "gc_percent", "n50_bp", "l50"},
    "coverage_estimate": {"estimated_x", "expected_genome_size_prior_bp"},
}
ACTION_PARAMS = {
    "no_change": {},
    "short_k": {"k": "21,33"},
    "auto_cutoff": {"cov_cutoff": "auto"},
}


class ModelDecision(BaseModel):
    """The model's entire structured answer, not an executable instruction."""
    model_config = ConfigDict(extra="forbid")

    diagnosis: Literal[
        "suspected_low_coverage", "suspected_adapter_contamination",
        "suspected_taxonomic_contamination", "suspected_high_error_rate",
        "no_strong_signal", "uncertain",
    ]
    severity: Literal["severe", "moderate", "mild", "not_assigned"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str]
    reasoning: str
    action: Literal["no_change", "short_k", "auto_cutoff"]
    action_reasoning: str
    limitations: list[str]


SYSTEM_PROMPT = """You are AGORA, an experimental bacterial-assembly QC diagnosis assistant.
You will receive one reference-free JSON profile, with no scenario labels.
Interpret the supplied measurements, keeping uncertainty explicit.
Coverage is a nominal estimate using a genome-size prior, not alignment depth.
Fragmentation alone is not diagnostic of low coverage. High Q30 is not proof
that adapters or contamination are absent. If evidence is insufficient, say so.

Choose one diagnosis from the structured schema. Choose one proposed action ONLY:
- no_change: preserve the default SPAdes assembly.
- short_k: experimental fixed SPAdes k-mer set 21,33.
- auto_cutoff: experimental SPAdes --cov-cutoff auto.
Do NOT request shell commands, file paths, downloads, arbitrary parameters,
new sequencing or unsanctioned processing. An action is a proposal, not executed.
If the data cannot justify a specific repair, prefer no_change and explain why.
Shorter k-mers/cutoff can worsen assemblies; maximizing N50 alone is not correctness.
Never claim to have measured genome fraction, NGA50 or misassemblies, because
reference-based results are hidden. Use evidence numbers from this profile only.
"""


def safe_profile(profile: object) -> dict:
    """Return strictly whitelisted fields; reject extras instead of silently dropping."""
    if not isinstance(profile, dict) or set(profile) != ALLOWED_KEYS[""]:
        raise ValueError("Profile must have exactly the four agent-safe top-level fields")
    if profile.get("schema_version") != "1.0":
        raise ValueError("Unsupported profile schema_version")
    result = {"schema_version": "1.0"}
    for section in ("read_qc", "assembly_qc", "coverage_estimate"):
        block = profile[section]
        if not isinstance(block, dict):
            raise ValueError(f"{section} must be an object")
        extras = set(block) - ALLOWED_KEYS[section]
        if extras:
            raise ValueError(f"Disallowed field(s) in {section}: {sorted(extras)}")
        if not block:
            raise ValueError(f"Missing data in {section}")
        for field in NUMERIC_FIELDS[section]:
            if field not in block:
                raise ValueError(f"Missing field {section}.{field}")
            value = block[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Invalid numeric field {section}.{field}")
        result[section] = block.copy()
    for section in ("read_qc", "assembly_qc"):
        for field in ("gc_percent",):
            if not 0 <= result[section][field] <= 100:
                raise ValueError(f"{section}.{field} outside 0..100")
    for field in ("q20_percent", "q30_percent", "n_percent"):
        if not 0 <= result["read_qc"][field] <= 100:
            raise ValueError(f"read_qc.{field} outside 0..100")
    if result["coverage_estimate"]["estimated_x"] <= 0:
        raise ValueError("coverage estimate must be positive")
    return result


def build_decision(profile: dict, prediction: ModelDecision, model: str) -> dict:
    """Post-validate model output and map action to immutable approved parameters."""
    if not prediction.evidence or not prediction.reasoning.strip() or not prediction.action_reasoning.strip():
        raise ValueError("Model decision missing required explanation")
    if len(prediction.evidence) > 12 or len(prediction.limitations) > 12:
        raise ValueError("Overly long evidence/limitations")
    payload = json.dumps(profile, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {
        "decision_schema_version": "0.2",
        "provider": "soclaas",
        "model": model,
        "profile_sha256": hashlib.sha256(payload).hexdigest(),
        "diagnosis": prediction.diagnosis,
        "severity": prediction.severity,
        "confidence": prediction.confidence,
        "evidence": prediction.evidence,
        "reasoning": prediction.reasoning,
        "action": {
            "name": prediction.action,
            "parameters": ACTION_PARAMS[prediction.action].copy(),
        },
        "action_reasoning": prediction.action_reasoning,
        "limitations": prediction.limitations,
        "executed": False,
    }


def get_prediction(profile: dict, model: str, client=None) -> ModelDecision:
    from soclaas_client import chat_json
    safe = safe_profile(profile)
    answer = chat_json(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + "\nReturn ONLY a JSON object with keys: diagnosis, severity, confidence, evidence, reasoning, action, action_reasoning, limitations. No markdown."},
            {"role": "user", "content": json.dumps(safe, separators=(",", ":"))},
        ],
        client=client,
    )
    return ModelDecision.model_validate(answer)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default=os.getenv("SOCLAAS_MODEL"))
    parser.add_argument("--validate-only", action="store_true", help="Check profile, no API call or output")
    args = parser.parse_args()

    if args.profile.stat().st_size > 64_000:
        raise ValueError("Profile exceeds 64 KB limit")
    profile = safe_profile(json.loads(args.profile.read_text(encoding="utf-8")))
    if args.validate_only:
        print("PASS: profile schema valid; restricted labels and reference metrics absent.")
        return
    if not args.model:
        raise SystemExit("Choose --model from `python scripts/soclaas_check.py` or set SOCLAAS_MODEL")
    if not os.environ.get("SOCLAAS_API_KEY"):
        raise SystemExit("Set SOCLAAS_API_KEY in this Ubuntu terminal (do not paste it into chat).")
    prediction = get_prediction(profile, args.model)
    decision = build_decision(profile, prediction, args.model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(decision, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved LLM proposal to: {args.output}")
    print(f"Diagnosis: {decision['diagnosis']} ({decision['severity']}, confidence={decision['confidence']:.2f})")
    print(f"Action (NOT executed): {decision['action']['name']}")


if __name__ == "__main__":
    main()
