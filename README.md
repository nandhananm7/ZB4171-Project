# AGORA — Milestone 1–2 Starter

This **starter** performs two assemblies of the same paired-end bacterial-read sample:

- `raw`: SPAdes with no external fastp preprocessing.
- `trimmed`: fastp default-style trimming then SPAdes.

Both assemblies are evaluated with **reference-free** QUAST. The comparison is written to `results/summary.json`.

This is only the core workflow. It does **not** yet inject failures, run CheckM2/Kraken2, call an LLM, or evaluate against a reference.

## 0. Prerequisites

Linux or Ubuntu in WSL2; Conda/Miniforge installed, 4 CPU cores recommended, at least 8 GB RAM (12–16 GB preferred), and **20+ GB free disk** for the full SRA extraction and scratch files. Run the project from Linux home storage (`~/AGORA_starter`) if using WSL2.

## 1. Install software

```bash
conda env create -f environment.yml
conda activate agora-mvp
snakemake --version
spades.py --version
fastp --version
quast.py --version
```

## 2. Download E. coli MG1655 Illumina reads and create a subset

The source accession is **ERR008613** from NCBI SRA (paired 2x100-bp reads). Do not use the reference genome during agent decisions.

```bash
bash scripts/download_and_subset.sh
```

This makes `data/subset/ecoli_R1.fastq.gz` and `ecoli_R2.fastq.gz`, sampling **1,200,000 pairs** with seed 42. At 2 × 100 bp, that is around 52x nominal coverage of a 4.64-Mbp bacterial genome (actual coverage depends on trimming and data quality).

**Note:** The download converts a large SRA accession to uncompressed FASTQ and needs ample scratch space. Raw files are retained to support future experiments. If the download is already present, comment out the `fasterq-dump` line and rerun only the sampling commands.

## 3. Build the workflow

Dry-run first:

```bash
snakemake -n --cores 4
```

Then run:

```bash
snakemake --cores 4 --printshellcmds
```

Expected outputs:

```text
results/raw/spades/contigs.fasta
results/raw/quast/report.tsv
results/trimmed/fastp/fastp.json
results/trimmed/fastp/fastp.html
results/trimmed/spades/contigs.fasta
results/trimmed/quast/report.tsv
results/summary.json
```

To inspect:

```bash
cat results/summary.json
python -m json.tool results/summary.json
```

## 4. Completion criterion

- Both raw and trimmed assemblies finish successfully.
- QUAST produces contig count, total assembled length, N50, largest contig, and GC%.
- `results/summary.json` has a `raw`, a `trimmed`, and a `fastp` section.
- No reference genome was used to produce or select these outputs.

## Important design notes for later milestones

- **No reference leakage:** Reference-based QUAST belongs to an evaluation script after an agent run is finished. The agent and controller's best-run selection use reference-free diagnostics only.
- **Low coverage is not repairable by parameter choice:** You cannot recover missing sequencing information. Judge this as diagnosis + avoiding harmful changes; consider a scenario-specific ceiling, not necessarily the full-depth clean assembly.
- **SPAdes already performs read error correction by default.** `--only-assembler` turns that stage off; do not call “turning correction on” a novel fix when it is already the default.
- **Contamination removal needs a method:** A later milestone can add Kraken2 with a taxonomy database and documented target-taxon assumptions. The absence of a *sample reference genome* is not the absence of all external biological databases.
- **Reproducibility:** Fix injection seeds, record accession checksums, pin environment versions and keep the injection labels outside the agent-visible JSON.

## Resources

- Snakemake installation: https://snakemake.readthedocs.io/en/stable/getting_started/installation.html
- SPAdes command line: https://ablab.github.io/spades/running.html
- fastp: https://github.com/OpenGene/fastp
- NCBI SRA accession: https://www.ncbi.nlm.nih.gov/sra/ERR008613
- QUAST: https://quast.sourceforge.net/
