# AGORA Milestone 7 — Held-out seed replication

This patch **only adds scripts and tests**. It does not modify existing workflow, controller, or evaluation files. It creates isolated frozen workspaces under `results/holdouts/seed_<seed>/` so changing the injection seed never overwrites the original four-scenario experiment.

## Setup

From your `ZB4171-Project` directory, after unzipping:

```bash
python -m unittest discover -s tests -p 'test_agora_holdout.py' -v
export SOCLAAS_MODEL="qwen3.8:27b" # or the exact model used for original experiments
```

## Pilot: seed 3101, clean + adapter

```bash
python scripts/agora_holdout.py prepare --seed 3101

# Run the clean input first to construct its clean-control comparator.
python scripts/agora_holdout.py run --seed 3101 --scenario clean --backend rule --mode iterative --cores 4
python scripts/agora_holdout.py run --seed 3101 --scenario clean --backend llm --mode iterative --cores 4

# Adapter-only example.
python scripts/agora_holdout.py run --seed 3101 --scenario adapter --backend rule --mode iterative --cores 4
python scripts/agora_holdout.py run --seed 3101 --scenario adapter --backend llm --mode iterative --cores 4

# Then evaluate with the reference *outside* the agent workflow.
python scripts/agora_holdout.py evaluate --seed 3101 --scenario clean --reference data/reference/NC_000913.3.fasta --cores 4
python scripts/agora_holdout.py evaluate --seed 3101 --scenario adapter --reference data/reference/NC_000913.3.fasta --cores 4
python scripts/agora_holdout.py status --seed 3101
```

For a complete replication, also run `rule/llm × zero/iterative` on all four scenarios and evaluate all four. Each seed gets separate reads, profiles, agent logs, and reference evaluations. The benchmark source genome remains outside model prompts.

## After the pilot: complete the remaining combinations

Prepare two more seeds in separate folders:

```bash
python scripts/agora_holdout.py prepare --seed 3102
python scripts/agora_holdout.py prepare --seed 3103
```

For each seed, run every scenario × backend × mode. You can use this loop;
it safely skips existing completed audits rather than overwriting them:

```bash
for seed in 3101 3102 3103; do
  for scenario in clean adapter quality combined; do
    for backend in rule llm; do
      for mode in zero iterative; do
        audit="results/holdouts/seed_${seed}/results/agent_runs/${scenario}/${backend}_${mode}.json"
        if [ ! -f "$audit" ]; then
          python scripts/agora_holdout.py run --seed "$seed" --scenario "$scenario" \
            --backend "$backend" --mode "$mode" --cores 4 || exit 1
        fi
      done
    done
    python scripts/agora_holdout.py evaluate --seed "$seed" --scenario "$scenario" \
      --reference data/reference/NC_000913.3.fasta --cores 4 || exit 1
  done
done
```

This can require substantial CPU time and disk space. Run the one-seed pilot
first and inspect its results before starting the full loop.

## Aggregate report

```bash
python scripts/agora_holdout_summary.py --seeds 3101 3102 3103
cat results/evaluation/heldout_summary/Heldout_Seed_Report.md
```

## Practical notes

- The runner copies the original preprocessed FASTQ files to each workspace for isolation; you need disk space for the reads and especially for new SPAdes assemblies.
- Every seed changes **the random positions of simulated defects**, not their probabilities (`adapter_rate=0.25`, `error_rate=0.35` by default).
- The original results in `results/challenges/` and `results/agent_runs/` are not used as the working files for the new seed runs.
- The runner hashes the frozen source snapshot; changing the snapshot causes future runs to be refused. To start over safely, choose a new unused seed, rather than deleting an existing dataset.
- The runner copies the project source and preprocessed reads. If source Snakemake scripts or configurations differ from the currently-installed extension, inspect the dry run first.
- API timeouts should be retried with the same seed/model; the script refuses overwriting a successful audit but permits retry after an incomplete run.
- The summary is **benchmark-only** and should never be imported into the agent.
