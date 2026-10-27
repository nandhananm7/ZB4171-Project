# AGORA: Milestone 3 — Low-coverage benchmark

Copy/merge this project into your existing ZB4171-Project directory. Keep all existing
`data/`, `results/`, `logs/` files. This starter extends the original Snakefile.

The source FASTQs come from the completed `fastp` step, NOT the untrimmed source.
The benchmark uses the published MG1655 genome length (4,641,652 bp) only to
select read-pair counts; it DOES NOT give the reference sequence to an agent.

## First: confirm the existing result is still present
```bash
ls -lh results/summary.json results/trimmed/reads/R1.fastq.gz results/trimmed/reads/R2.fastq.gz
```

## Dry run of a single test
```bash
snakemake -n --cores 4 results/lowcov/15x/quast/report.tsv
```

## Run one scenario first
```bash
snakemake --cores 4 --printshellcmds results/lowcov/15x/quast/report.tsv
cat data/failures/lowcov/15x/metadata.json
cat results/lowcov/15x/quast/report.tsv
```

## Then run the full experiment
```bash
snakemake -n --cores 4 results/lowcov/summary.json
snakemake --cores 4 --printshellcmds results/lowcov/summary.json
python -m json.tool results/lowcov/summary.json
```

## Notes
- Same integer sample count and seed for each mate preserves paired-end reads.
- A different, recorded fixed seed is used for each coverage (42 + coverage).
- The code validates every sampled pair and counts total bases to measure nominal coverage.
- `benchmark_metadata` is the experimental ground truth: never feed it to the LLM.
- Keep a copy of the original `Snakefile` and `config.yaml` before replacing.
- Outputs are reference-free, so higher N50 is not proof of better genome accuracy.
- Always run within WSL/Ubuntu with `conda activate agora-mvp`.
- Assemble one at a time with --cores 4 on machines with ~8GB RAM.
