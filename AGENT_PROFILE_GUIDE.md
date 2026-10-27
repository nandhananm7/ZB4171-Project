# AGORA — Milestone 5A: Agent-safe diagnostic input

This patch adds *new files only*. It does not modify your existing Snakefile or config.yaml, assemblies, benchmark metadata, or QUAST reference evaluations.

## Install in your existing project folder

```bash
cp Snakefile Snakefile.pre_agent_profiles.bak
unzip -o /mnt/c/Users/nandh/Downloads/AGORA_agent_safe_patch.zip -d .
grep -q 'include: "workflow/agent_profiles.smk"' Snakefile || printf '\ninclude: "workflow/agent_profiles.smk"\n' >> Snakefile
```

## Test and build the first profile

```bash
python -m unittest discover -s tests -p 'test_agent_profile.py' -v
snakemake -n --cores 4 results/agent_profiles/8x/profile.json
snakemake --cores 4 --printshellcmds results/agent_profiles/8x/profile.json
python -m json.tool results/agent_profiles/8x/profile.json
```

If successful, optionally build all the profiles:

```bash
snakemake --cores 4 results/agent_profiles/15x/profile.json results/agent_profiles/30x/profile.json results/agent_profiles/full/profile.json
```

## Intentional limitations

- The profile contains no reference FASTA, no benchmark metadata, and no reference-aligned metrics (NGA50, genome fraction, misassemblies, mismatch rate).
- Coverage is approximated as sequenced bases / 4,600,000 bp, a **species-size prior** for E. coli, rather than read alignment to the evaluation reference or a value read from injection metadata.
- Nominal depth may be misleading under contamination, bias, or mixed-species data. Later versions should use reference-free k-mer spectra and contamination-aware QC.
- Agent/controller must pass **only JSON content**; the file path's `8x` / `15x` / `30x` label and folder names are benchmark metadata and must not appear in the model prompt.
- This is not yet diagnosis or automated repair. It is the controlled input for those systems.
