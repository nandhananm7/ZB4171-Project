# AGORA: Milestone 4A — controlled SPAdes repair-action tests

Do **not** replace your existing Snakefile or config.yaml. Copy these two new
files into your current project, retaining their subdirectories:

- `workflow/lowcov_repair.smk`
- `scripts/compare_repair.py`

Append exactly once at the END of your existing Snakefile:

```
include: "workflow/lowcov_repair.smk"
```

Do not edit `rule all` yet. First verify the single-target dry run:

```
snakemake -n --cores 4 results/repair/8x/short_k/quast/report.tsv
```

Run the first ablation, with read correction preserved in both strategies:

```
snakemake --cores 4 --printshellcmds results/repair/8x/short_k/quast/report.tsv
python scripts/compare_repair.py --coverage 8 --strategy short_k
```

The candidate action uses `-k 21,33`; the pre-existing default run uses
SPAdes' automatic k-mer selection. The default for 100 bp reads is normally
21,33,55 (per official SPAdes documentation).

Only after reviewing the first result, optionally run:

```
snakemake --cores 4 --printshellcmds results/repair/15x/short_k/quast/report.tsv
python scripts/compare_repair.py --coverage 15 --strategy short_k
```

For a separate graph-filtering experiment, use strategy `auto_cutoff` instead.
`--cov-cutoff auto` is not necessarily an appropriate fix for low coverage;
test it as a *hypothesis*, not a guaranteed improvement.

Both variants use the SAME sampled reads as the existing results.
`metadata.json` contains scenario labels and construction metadata; do NOT
send it to the future LLM agent. The current output is exploratory
reference-free QC, not a correctness or recovery score.

To monitor a running 8x short_k job:

```
watch -n 10 'tail -n 12 logs/repair_8x_short_k_spades.log'
```

These new outputs are in `results/repair/`, isolated from the completed
`results/lowcov/` and `results/summary.json` experiments.
