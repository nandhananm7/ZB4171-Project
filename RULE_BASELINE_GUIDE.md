# AGORA Milestone 5A — first deterministic rule-based baseline

This is a **diagnostic prototype for low coverage only**, not the final multi-problem rule-based comparator.
It reads only the contents of a provided agent-safe profile JSON; it does not read file paths, injected failure labels, benchmark metadata, reference FASTA files or reference-based QUAST output.

## Install

Unzip into the top-level project directory. No Snakefile modifications are required.

## Verify unit tests

```bash
python -m unittest discover -s tests -p 'test_rule_based_agent.py' -v
```

## Run first case

```bash
python scripts/rule_based_agent.py \
    --profile results/agent_profiles/8x/profile.json \
    --output results/rule_based/8x/decision.json
python -m json.tool results/rule_based/8x/decision.json
```

## After generating remaining agent profiles

```bash
snakemake --cores 4 \
  results/agent_profiles/15x/profile.json \
  results/agent_profiles/30x/profile.json \
  results/agent_profiles/full/profile.json

for sample in 8x 15x 30x full; do
  python scripts/rule_based_agent.py \
    --profile "results/agent_profiles/$sample/profile.json" \
    --output "results/rule_based/$sample/decision.json"
done
```

## Scientific caveats

* Coverage cutoffs (<10x severe, 10-20x moderate) are intentionally simple, editable heuristics, not clinically or scientifically calibrated probabilities.
* The `no_change` recommendation is a conservative control; it does not claim to repair inadequate depth.
* Read statistics and reference-free QUAST cannot reliably diagnose all defects. Extend the rule-based baseline to adapters, contamination and sequencing errors before the full comparative benchmark.
* Freeze rules and actions before evaluation on new held-out datasets/seeds; earlier hand-inspected cases are developmental, not independent validation.
* Do not show scenario folder names (`8x`) to an LLM. The command-line path here is used by the controller only.
