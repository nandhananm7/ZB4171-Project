# AGORA: Controlled multi-problem repair extension

This patch is an **add-on** to the AGORA project already built (Snakemake, fastp,
SPAdes, QUAST, and `scripts/build_agent_profile.py`). It does **not** modify
or delete any prior low-coverage experiment or assembly.

## Scientific scope

- Four deterministic *paired* data variants from the same preprocessed E. coli
  FASTQs: `clean`, `adapter`, `quality`, `combined`.
- The synthetic adapter artifact replaces the 3' tail with a standard Illumina
  adapter prefix on selected reads. The error artifact reduces tail quality
  to Q10 and introduces random substitutions with probability 0.10 for
  selected reads. These are **simplified synthetic artifacts**, not a
  physically calibrated Illumina error model.
- Reference-free measurements (including a standard adapter motif near the read
  end, tail quality, N50, contig count, and *nominal* depth) are the **only**
  observations supplied to either policy.
- Both agent types select from the **same action whitelist** and rerun from
  the exact same original corrupted FASTQs: `fastp_default`,
  `explicit_adapter`, `quality_trim`, `adapter_quality`, or `stop`.
- The controller executes a fixed number of attempts and uses a **predefined,
  heuristic reference-free safety check** to decide whether a trial is
  preferable to the unmodified assembly. No claim of correctness improvement
  is made until independent reference-based evaluation.
- The offline `mock` policy tests orchestration **only**; it is **not an LLM**.

## Install (Ubuntu/WSL2, in the existing project root)

Unzip the patch **into the project root** so `scripts/`, `tests/` and
`workflow/` merge with existing directories. Do not replace the existing
Snakefile.

```bash
cd /mnt/c/Users/nandh/Documents/ZB4171-Project
conda activate agora-mvp
unzip -o /mnt/c/Users/nandh/Downloads/AGORA_iterative_extension.zip -d .
# only once (append at the END of existing Snakefile)
grep -q 'include: "workflow/agora_challenge.smk"' Snakefile || \
  printf '\ninclude: "workflow/agora_challenge.smk"\n' >> Snakefile
python -m unittest discover -s tests -p 'test_agora_extension.py' -v
```

The separate `scripts/agora_*.py` names avoid overwriting existing scripts.
The default `max_pairs=600000` yields roughly 25x nominal depth for 100bp
paired reads; change the optional `agora_challenge.max_pairs` in `config.yaml`
to `1000000` for ~43x if stronger assembly performance is needed. Existing
read subsets were sampled previously, so the first 600k pairs are a bounded
*development subset*, not an independently random sample from SRA.

Optionally add to existing `config.yaml` (no change needed for defaults):

```yaml
agora_challenge:
  max_pairs: 600000
  seed: 2026
  genome_size_prior: 4600000
```

## A. Dry run and validate the synthetic challenge

```bash
snakemake -n --cores 4 results/challenges/combined/raw/profile.json
snakemake --cores 4 results/challenges/combined/raw/profile.json
python -m json.tool data/challenges/combined/benchmark_metadata.json
python -m json.tool results/challenges/combined/raw/profile.json
```

**Never** provide `benchmark_metadata.json` to the rule-based agent or LLM.
The model receives only `profile.json` contents and a numerical baseline plus history of
previous attempts. It never receives the scenario name, path, reference FASTA,
QUAST-with-reference results, or a pre-written ideal answer.

## B. Conventional baseline (fastp defaults) vs corrupted raw

```bash
snakemake --cores 4 results/challenges/combined/fastp_default/profile.json
```

The original input reads had already been fastp-cleaned before synthetic
corruption was applied. This controlled experiment therefore compares
no *additional* preprocessing vs conventional fastp on that corrupted input.
The standard fastp pipeline is a genuine comparator and must not be disabled
in reported experiments.

## C. Offline end-to-end iterative controller (no API charge)

```bash
python scripts/agora_controller.py --scenario combined --backend mock \
    --mode iterative --max-steps 2 --cores 4 --dry-plan
python scripts/agora_controller.py --scenario combined --backend mock \
    --mode iterative --max-steps 2 --cores 4
```

The mock backend deliberately makes predetermined proposals; it demonstrates
that the controller reruns and evaluates allowed actions, **not** that AI
reasoning works.

## D. Rule baseline, zero-shot and iterative LLM

```bash
python scripts/agora_controller.py --scenario combined --backend rule \
  --mode iterative --max-steps 2 --cores 4
python scripts/agora_controller.py --scenario combined --backend rule \
  --mode zero --cores 4
```

For live LLM (API charges):

```bash
python -m pip install 'openai>=2' 'pydantic>=2'
read -rsp 'OpenAI API key: ' OPENAI_API_KEY; echo
export OPENAI_API_KEY
python scripts/agora_controller.py --scenario combined --backend llm \
  --mode zero --cores 4 --model gpt-5-mini
python scripts/agora_controller.py --scenario combined --backend llm \
  --mode iterative --max-steps 2 --cores 4 --model gpt-5-mini
```

Outputs: `results/agent_runs/combined/{rule,llm,mock}_{zero,iterative}.json`.
Every trial produces separate `results/challenges/<scenario>/<action>/...` files.
Two runs can reuse already completed Snakemake jobs. Do not run Snakemake
concurrently against the same output tree. No model response runs shell code.

A policy may stop or select the original `raw` assembly, and iterative trials
may fail to improve the reference-free QC. These are valid results.

## E. Independent REFERENCE evaluation (after policy decisions)

Before running, make sure the reference FASTA from your prior work exists.
Build a clean comparison once:

```bash
snakemake --cores 4 results/challenges/clean/raw/profile.json
python scripts/agora_evaluate.py --scenario combined \
  --reference data/reference/NC_000913.3.fasta --cores 4
cat results/evaluation/challenges/combined/report.tsv
python -m json.tool results/evaluation/challenges/combined/comparison.json
```

**Run this only after all decisions have been written.** Reference metrics
are not imported into the policy or controller. `evaluation_status` remains
`reference_free_only` in agent runs.

## F. Controlled comparison

Create datasets for the other failure classes, and repeat the comparisons:

```bash
snakemake --cores 4 results/challenges/adapter/raw/profile.json \
  results/challenges/quality/raw/profile.json
python scripts/agora_controller.py --scenario adapter --backend rule --mode iterative
python scripts/agora_controller.py --scenario quality --backend rule --mode iterative
```

Freeze rule thresholds and action menus before held-out testing; vary injection
seeds and severity only on a new experiment version or separately named run
folder. These scenarios at one seed are development experiments, **not** proof
that iterative LLM decisions are better. Fair final comparisons require
held-out seeds, replicated runs and the same budgets and inputs.

## Interpretation and caveats

- Clean control should favor restraint. Default fastp can already handle
  adapters; improvements are not guaranteed. If it wins, report that.
- This patch models adapter tails and erroneous low-quality bases, NOT species
  contamination, experiment batch effects or RNA-seq GTF configuration.
- Q30 of surviving reads can increase simply because reads were discarded.
- The heuristic controller uses a 2% assembly-length loss guard, 10% N50 loss
  guard, and 10% contig-count increase guard; it may make incorrect choices.
  Reference-based QUAST is the independent arbiter.
- To test different seeds without mixing Snakemake cached results, work in a
  separate project copy or change the output directory naming and re-run;
  do not quietly overwrite earlier results.
- Running from WSL2's `/mnt/c/` is often slower than the Linux filesystem.
