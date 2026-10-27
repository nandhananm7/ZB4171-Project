"""Controlled SPAdes repair-action experiments for the AGORA low-coverage benchmark.

Requires variables THREADS, MEMORY_GB from existing Snakefile and sample files
produced by workflow/lowcov.smk. Existing results are never overwritten.
"""

REPAIR_ACTIONS = {
    # Deliberate ablation against default multi-k SPAdes for ~100bp reads.
    "short_k": "-k 21,33",
    # Test graph coverage filtering; can hurt true low-coverage reads.
    "auto_cutoff": "--cov-cutoff auto",
}


rule assemble_lowcov_repair:
    input:
        r1="data/failures/lowcov/{coverage}x/R1.fastq.gz",
        r2="data/failures/lowcov/{coverage}x/R2.fastq.gz"
    output:
        "results/repair/{coverage}x/{strategy}/spades/contigs.fasta"
    params:
        options=lambda wc: REPAIR_ACTIONS[wc.strategy],
        outdir=lambda wc: f"results/repair/{wc.coverage}x/{wc.strategy}/spades",
        memory=MEMORY_GB
    threads: THREADS
    log:
        "logs/repair_{coverage}x_{strategy}_spades.log"
    wildcard_constraints:
        coverage="8|15|30",
        strategy="short_k|auto_cutoff"
    shell:
        r"""
        mkdir -p logs {params.outdir:q}
        spades.py -1 {input.r1:q} -2 {input.r2:q} {params.options} \
            --threads {threads} --memory {params.memory} \
            -o {params.outdir:q} > {log:q} 2>&1
        """


rule quast_lowcov_repair:
    input:
        "results/repair/{coverage}x/{strategy}/spades/contigs.fasta"
    output:
        "results/repair/{coverage}x/{strategy}/quast/report.tsv"
    params:
        outdir=lambda wc: f"results/repair/{wc.coverage}x/{wc.strategy}/quast"
    threads: THREADS
    log:
        "logs/repair_{coverage}x_{strategy}_quast.log"
    wildcard_constraints:
        coverage="8|15|30",
        strategy="short_k|auto_cutoff"
    shell:
        r"""
        mkdir -p logs
        quast.py {input:q} --threads {threads} \
            -o {params.outdir:q} > {log:q} 2>&1
        """
