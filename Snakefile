configfile: "config.yaml"

R1 = config["reads"]["r1"]
R2 = config["reads"]["r2"]
THREADS = int(config.get("threads", 4))
MEMORY_GB = int(config.get("memory_gb", 8))


rule all:
    input:
        "results/summary.json",
        "results/lowcov/summary.json"


rule fastp:
    input:
        r1=R1,
        r2=R2
    output:
        r1="results/trimmed/reads/R1.fastq.gz",
        r2="results/trimmed/reads/R2.fastq.gz",
        json="results/trimmed/fastp/fastp.json",
        html="results/trimmed/fastp/fastp.html"
    threads: THREADS
    log:
        "logs/fastp.log"
    shell:
        """
        mkdir -p results/trimmed/reads results/trimmed/fastp logs
        fastp -i {input.r1} -I {input.r2} -o {output.r1} -O {output.r2} \
            --detect_adapter_for_pe --thread {threads} \
            --json {output.json} --html {output.html} > {log} 2>&1
        """


rule assemble_raw:
    input:
        r1=R1,
        r2=R2
    output:
        "results/raw/spades/contigs.fasta"
    threads: THREADS
    params:
        memory=MEMORY_GB
    log:
        "logs/spades_raw.log"
    shell:
        """
        mkdir -p results/raw/spades logs
        spades.py -1 {input.r1} -2 {input.r2} \
            --threads {threads} --memory {params.memory} \
            -o results/raw/spades > {log} 2>&1
        """


rule assemble_trimmed:
    input:
        r1="results/trimmed/reads/R1.fastq.gz",
        r2="results/trimmed/reads/R2.fastq.gz"
    output:
        "results/trimmed/spades/contigs.fasta"
    threads: THREADS
    params:
        memory=MEMORY_GB
    log:
        "logs/spades_trimmed.log"
    shell:
        """
        mkdir -p results/trimmed/spades logs
        spades.py -1 {input.r1} -2 {input.r2} \
            --threads {threads} --memory {params.memory} \
            -o results/trimmed/spades > {log} 2>&1
        """


rule quast_raw:
    input:
        "results/raw/spades/contigs.fasta"
    output:
        "results/raw/quast/report.tsv"
    threads: THREADS
    log:
        "logs/quast_raw.log"
    shell:
        """
        mkdir -p results/raw/quast logs
        quast.py {input} --threads {threads} -o results/raw/quast > {log} 2>&1
        """


rule quast_trimmed:
    input:
        "results/trimmed/spades/contigs.fasta"
    output:
        "results/trimmed/quast/report.tsv"
    threads: THREADS
    log:
        "logs/quast_trimmed.log"
    shell:
        """
        mkdir -p results/trimmed/quast logs
        quast.py {input} --threads {threads} -o results/trimmed/quast > {log} 2>&1
        """


rule summarize:
    input:
        raw="results/raw/quast/report.tsv",
        trimmed="results/trimmed/quast/report.tsv",
        fastp="results/trimmed/fastp/fastp.json"
    output:
        "results/summary.json"
    log:
        "logs/summary.log"
    shell:
        """
        python scripts/summarize_quast.py \
            --raw {input.raw} --trimmed {input.trimmed} \
            --fastp {input.fastp} --output {output} > {log} 2>&1
        """


# Additional benchmark workflow. The original baseline rules above are unchanged.
include: "workflow/lowcov.smk"

include: "workflow/lowcov_repair.smk"

include: "workflow/agent_profiles.smk"

include: "workflow/agora_challenge.smk"
