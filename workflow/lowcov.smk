# Low-coverage benchmark: deterministic paired subsamples of preprocessed reads.
# This file is included by the original Snakefile.

LOWCOV = config["low_coverage"]
COVERAGES = [int(x) for x in LOWCOV["targets_x"]]

rule create_lowcov_reads:
    input:
        r1="results/trimmed/reads/R1.fastq.gz",
        r2="results/trimmed/reads/R2.fastq.gz",
        fastp="results/trimmed/fastp/fastp.json"
    output:
        r1="data/failures/lowcov/{coverage}x/R1.fastq.gz",
        r2="data/failures/lowcov/{coverage}x/R2.fastq.gz",
        metadata="data/failures/lowcov/{coverage}x/metadata.json"
    params:
        genome_bp=int(LOWCOV["genome_size_bp"]),
        seed=int(LOWCOV["seed"])
    threads: THREADS
    log: "logs/lowcov_{coverage}x_sample.log"
    shell:
        """
        mkdir -p logs
        python scripts/make_lowcov.py \
            --r1 {input.r1:q} --r2 {input.r2:q} --fastp {input.fastp:q} \
            --coverage {wildcards.coverage} --genome-bp {params.genome_bp} \
            --seed {params.seed} --threads {threads} \
            --out-r1 {output.r1:q} --out-r2 {output.r2:q} \
            --metadata {output.metadata:q} > {log:q} 2>&1
        """

rule assemble_lowcov:
    input:
        r1="data/failures/lowcov/{coverage}x/R1.fastq.gz",
        r2="data/failures/lowcov/{coverage}x/R2.fastq.gz"
    output:
        "results/lowcov/{coverage}x/spades/contigs.fasta"
    params:
        memory=MEMORY_GB
    threads: THREADS
    log: "logs/lowcov_{coverage}x_spades.log"
    shell:
        """
        mkdir -p logs results/lowcov/{wildcards.coverage}x
        spades.py -1 {input.r1:q} -2 {input.r2:q} \
            --threads {threads} --memory {params.memory} \
            -o results/lowcov/{wildcards.coverage}x/spades > {log:q} 2>&1
        """

rule quast_lowcov:
    input:
        "results/lowcov/{coverage}x/spades/contigs.fasta"
    output:
        "results/lowcov/{coverage}x/quast/report.tsv"
    threads: THREADS
    log: "logs/lowcov_{coverage}x_quast.log"
    shell:
        """
        mkdir -p logs
        quast.py {input:q} --threads {threads} \
            -o results/lowcov/{wildcards.coverage}x/quast > {log:q} 2>&1
        """

rule summarize_lowcov:
    input:
        full="results/trimmed/quast/report.tsv",
        reports=expand("results/lowcov/{coverage}x/quast/report.tsv", coverage=COVERAGES),
        metadata=expand("data/failures/lowcov/{coverage}x/metadata.json", coverage=COVERAGES)
    output:
        "results/lowcov/summary.json"
    params:
        labels=" ".join(map(str, COVERAGES))
    log: "logs/lowcov_summary.log"
    shell:
        """
        python scripts/summarize_lowcov.py \
            --baseline {input.full:q} \
            --coverages {params.labels} \
            --reports {input.reports:q} \
            --metadata {input.metadata:q} \
            --output {output:q} > {log:q} 2>&1
        """
