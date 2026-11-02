# AGORA — Cross-scenario results summary (Milestone 6)

This is **only a benchmark/reporting component**. Never import `agora_summary.py` from agent code or put its output inside LLM prompts: it contains reference-dependent QUAST metrics and injected scenario labels.

## Install

Extract `AGORA_evaluation_summary_patch.zip` into the **root** of your current `ZB4171-Project` directory. This adds `scripts/agora_summary.py` and `tests/test_evaluation_summary.py`; it does not overwrite the Snakefile, decision code, or existing results.

## 1. Complete all four reference evaluations

With your Conda environment active, from the AGORA project root:

```bash
for scenario in clean adapter quality combined; do
  python scripts/agora_evaluate.py \
    --scenario "$scenario" \
    --reference data/reference/NC_000913.3.fasta \
    --cores 4
done
```

Rerunning this is important if you generated new `rule_zero` / `llm_zero` logs after a prior evaluation, since the comparison JSON is a snapshot of available strategies at evaluation time.

## 2. Create the summary

```bash
python scripts/agora_summary.py
```

Outputs:
- `results/evaluation/summary/agora_comparison.csv`: all evaluated pipelines, strategies, and metrics
- `results/evaluation/summary/agent_decisions.csv`: first diagnoses, actions, final selection and trials
- `results/evaluation/summary/AGORA_Cross_Scenario_Report.md`: report-ready Markdown tables

## 3. Verify basic coverage and decisions

```bash
python -m unittest discover -s tests -p 'test_evaluation_summary.py' -v
head -n 8 results/evaluation/summary/agora_comparison.csv
cat results/evaluation/summary/AGORA_Cross_Scenario_Report.md
```

## Interpretation

- Category-match rates reflect four injected scenario labels, not held-out biological accuracy.
- The controller's `acceptable=True` flag is based on *reference-free* heuristics, not reference correctness.
- NGA50 is reference-dependent and **not** a metric to give to the agent during decision-making.
- If a `STALE` warning appears, rerun `scripts/agora_evaluate.py` for that scenario, then rerun the summary.
- Do not alter prompts or thresholds based solely on these four cases. Freeze the settings and test unseen injection strengths/seeds when feasible.
