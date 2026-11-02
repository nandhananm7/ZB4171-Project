# AGORA Milestone 9 — Controlled Feedback Ablation

This is an **add-on**: it does not replace `agora_controller.py`, edit the rule-based agent, or modify the earlier results. It uses the existing SoCLaaS `decide("llm", ...)` pathway and strict reference-free QC schema.

## Question

Does revealing the *result of a fixed initial repair* change an LLM's **second action** and the resulting assembly, compared with withholding the repair feedback?

## Protocol

For each scenario, **both conditions** see:

- Identical original read/assembly QC (`profile=raw/profile.json`).
- Identical initial `baseline_observation`.
- The same first repair in `history[0]['action']`.
- The same AGORA system prompt, model and provider-default decoding configuration.

Only three `history[0]` fields differ:

| Field | `no_feedback` control | `feedback` treatment |
|---|---|---|
| `result` | `null` | Real first-trial reference-free summary |
| `acceptable` | `null` | Frozen reference-free controller guard result |
| `explanation` | `null` | Frozen guard explanation |

No condition receives the injected scenario label, random seed, source path, reference genome, NGA50 or any reference-based QUAST measurements.

One repetition consists of **two independent LLM calls**, one per condition. Order is randomized reproducibly using the chosen order seed; completed calls are skipped on rerun. Responses are schema-checked by the *existing* `agora_decide.decide()` implementation.

When benchmarking afterward, the tool replays the controller's existing `acceptable()` and `quality_score()` rules over the fixed first action and the newly proposed second action, using **existing, precomputed action-specific profiles**. No simulated cumulative trimming: every repair refers to the original read pairs. The benchmark uses QUAST with a reference in a *separate command after decisions are recorded*.

### Limitations

- This is a **matched-original-profile design**, not a verbatim reproduction of the production controller's post-trial `current=candidate` input. We deliberately keep the `profile` constant in both arms so only the feedback fields differ.
- Unspecified SoCLaaS temperature/seed and backend scheduling can still produce variation; interleaved calls reduce time-order confounding but are not a deterministic model-seed experiment.
- A proposed but unavailable second action **is not executed**; it is marked incomplete and excluded from complete paired benchmark comparison. The summary never silently counts it as a failed repair.
- The guard is reference-free and can accept repairs that worsen reference-based metrics. QUAST is solely an external evaluation.
- 10 pairs per scenario are descriptive; don't treat them as independent biological replicates or make a single-metric 'winner' claim.

## Installation

Unzip from Windows Downloads into the existing AGORA project:

```bash
cd /mnt/c/Users/nandh/Documents/ZB4171-Project
conda activate agora-mvp
unzip -o /mnt/c/Users/nandh/Downloads/AGORA_Milestone9_feedback_ablation_patch.zip -d .
python -m unittest discover -s tests -p 'test_agora_feedback_ablation.py' -v
```

The patch adds only two scripts and one test file. It does not overwrite your original scripts.

## Pilot (seed 3101, combined scenario)

The fixed initial action is standard fastp; compare whether actual observed feedback encourages a second repair.

```bash
export SOCLAAS_MODEL="qwen3.8:27b"  # only if this is your frozen model
python scripts/agora_feedback_ablation.py run --seed 3101 --scenario combined \
  --first-action fastp_default --repetitions 3 --model "$SOCLAAS_MODEL"
```

If this succeeds, complete **10 paired repetitions**, automatically skipping the first 3:

```bash
python scripts/agora_feedback_ablation.py run --seed 3101 --scenario combined \
  --first-action fastp_default --repetitions 10 --model "$SOCLAAS_MODEL"
```

**No reference FASTA is used during `run`.**

## Independent evaluation (after decisions)

```bash
python scripts/agora_feedback_ablation.py evaluate --seed 3101 --scenario combined \
  --first-action fastp_default --repetitions 10 --model "$SOCLAAS_MODEL" \
  --reference data/reference/NC_000913.3.fasta --threads 4
```

Results are under:

```
results/evaluation/feedback_ablation/seed_3101/combined/fastp_default/qwen3.8_27b/
    manifest.json
    decisions.jsonl
    paired_decisions.csv
    summary.json
    REPORT.md
    BENCHMARK_ONLY_metrics.json
    BENCHMARK_ONLY_QUAST/
```

Inspect:

```bash
cat results/evaluation/feedback_ablation/seed_3101/combined/fastp_default/qwen3.8_27b/REPORT.md
```

## Remaining two scenarios

```bash
# Clean, fixed aggressive quality trim
python scripts/agora_feedback_ablation.py run --seed 3101 --scenario clean \
  --first-action quality_trim --repetitions 10 --model "$SOCLAAS_MODEL"
python scripts/agora_feedback_ablation.py evaluate --seed 3101 --scenario clean \
  --first-action quality_trim --repetitions 10 --model "$SOCLAAS_MODEL" \
  --reference data/reference/NC_000913.3.fasta --threads 4

# Adapter, fixed combined adapter + quality trim
python scripts/agora_feedback_ablation.py run --seed 3101 --scenario adapter \
  --first-action adapter_quality --repetitions 10 --model "$SOCLAAS_MODEL"
python scripts/agora_feedback_ablation.py evaluate --seed 3101 --scenario adapter \
  --first-action adapter_quality --repetitions 10 --model "$SOCLAAS_MODEL" \
  --reference data/reference/NC_000913.3.fasta --threads 4
```

Optional: also use `quality --first-action quality_trim` for a complete four-scenario comparison.

## Aggregate the scenarios

```bash
python scripts/agora_feedback_ablation_summary.py --seed 3101 --model "$SOCLAAS_MODEL"
cat results/evaluation/feedback_ablation/seed_3101/FINAL_ABLATION_SUMMARY.md
```

The analysis produces paired NGA50 changes, paired mismatch-rate changes and second-action frequencies. A treatment effect on second decisions is **not** proof that the reference-based assembly is always better.

## If a first-trial profile is missing

The tool will stop and show the missing profile. Build just that target in the isolated seed workspace, e.g.:

```bash
(cd results/holdouts/seed_3101 && snakemake --cores 4 \
  results/challenges/clean/quality_trim/profile.json)
```

If evaluation says a proposed **second action profile** is missing, finish only that action's Snakemake target in the seed workspace and rerun `evaluate`. QUAST evaluates only the assemblies that already exist; it never silently generates new ones.

## Validity check

The script refuses to combine successful decisions with modified input profiles, code or model identifiers in a previously created output directory. To run a revised prompt or model, keep the old directory and create a new experiment version in a separate snapshot rather than overwriting the old results.
