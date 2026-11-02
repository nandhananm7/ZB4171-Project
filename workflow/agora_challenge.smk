"""AGORA isolated adapter/quality challenges. No changes to original outputs.

Append: include: "workflow/agora_challenge.smk" to the existing Snakefile.
Uses THREADS and MEMORY_GB already defined by the root Snakefile.
"""
CHALLENGE_ACTIONS = {
    'fastp_default': '--detect_adapter_for_pe',
    'explicit_adapter': '--detect_adapter_for_pe --adapter_sequence AGATCGGAAGAGCACACGTCTGAACTCCAGTCA --adapter_sequence_r2 AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT',
    'quality_trim': '--detect_adapter_for_pe --cut_right --cut_right_window_size 4 --cut_right_mean_quality 25',
    'adapter_quality': '--detect_adapter_for_pe --adapter_sequence AGATCGGAAGAGCACACGTCTGAACTCCAGTCA --adapter_sequence_r2 AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT --cut_right --cut_right_window_size 4 --cut_right_mean_quality 25',
}
CHALLENGE_CONFIG = config.get('agora_challenge', {})
CHALLENGE_PAIRS = int(CHALLENGE_CONFIG.get('max_pairs', 600000))
CHALLENGE_SEED = int(CHALLENGE_CONFIG.get('seed', 2026))
CHALLENGE_GENOME_PRIOR = int(CHALLENGE_CONFIG.get('genome_size_prior', 4600000))

rule agora_challenge_inject:
    input:
        r1='results/trimmed/reads/R1.fastq.gz',
        r2='results/trimmed/reads/R2.fastq.gz'
    output:
        r1='data/challenges/{scenario}/R1.fastq.gz',
        r2='data/challenges/{scenario}/R2.fastq.gz',
        meta='data/challenges/{scenario}/benchmark_metadata.json'
    wildcard_constraints:
        scenario='clean|adapter|quality|combined'
    params:
        pairs=CHALLENGE_PAIRS, seed=CHALLENGE_SEED
    log: 'logs/agora_inject_{scenario}.log'
    shell:
        r"""
        mkdir -p logs
        python scripts/agora_inject.py --r1 {input.r1:q} --r2 {input.r2:q} \
          --out-r1 {output.r1:q} --out-r2 {output.r2:q} --metadata {output.meta:q} \
          --scenario {wildcards.scenario} --seed {params.seed} --max-pairs {params.pairs} > {log:q} 2>&1
        """

rule agora_challenge_fastp:
    input:
        r1='data/challenges/{scenario}/R1.fastq.gz',
        r2='data/challenges/{scenario}/R2.fastq.gz'
    output:
        r1='results/challenges/{scenario}/{action}/reads/R1.fastq.gz',
        r2='results/challenges/{scenario}/{action}/reads/R2.fastq.gz',
        qc='results/challenges/{scenario}/{action}/fastp.json',
        html='results/challenges/{scenario}/{action}/fastp.html'
    wildcard_constraints:
        scenario='clean|adapter|quality|combined',
        action='fastp_default|explicit_adapter|quality_trim|adapter_quality'
    params:
        flags=lambda wc: CHALLENGE_ACTIONS[wc.action]
    threads: THREADS
    log: 'logs/agora_fastp_{scenario}_{action}.log'
    shell:
        r"""
        mkdir -p logs results/challenges/{wildcards.scenario}/{wildcards.action}/reads
        fastp -i {input.r1:q} -I {input.r2:q} -o {output.r1:q} -O {output.r2:q} \
          --thread {threads} --json {output.qc:q} --html {output.html:q} \
          {params.flags} > {log:q} 2>&1
        """

def agora_assembly_input(wc, mate):
    if wc.action == 'raw':
        return f'data/challenges/{wc.scenario}/{mate}.fastq.gz'
    return f'results/challenges/{wc.scenario}/{wc.action}/reads/{mate}.fastq.gz'

rule agora_challenge_assemble:
    input:
        r1=lambda wc: agora_assembly_input(wc, 'R1'),
        r2=lambda wc: agora_assembly_input(wc, 'R2')
    output:
        'results/challenges/{scenario}/{action}/spades/contigs.fasta'
    wildcard_constraints:
        scenario='clean|adapter|quality|combined',
        action='raw|fastp_default|explicit_adapter|quality_trim|adapter_quality'
    params:
        output_dir=lambda wc: f'results/challenges/{wc.scenario}/{wc.action}/spades',
        memory=MEMORY_GB
    threads: THREADS
    log: 'logs/agora_spades_{scenario}_{action}.log'
    shell:
        r"""
        mkdir -p logs
        spades.py -1 {input.r1:q} -2 {input.r2:q} --threads {threads} \
          --memory {params.memory} -o {params.output_dir:q} > {log:q} 2>&1
        """

rule agora_challenge_quast:
    input:
        'results/challenges/{scenario}/{action}/spades/contigs.fasta'
    output:
        'results/challenges/{scenario}/{action}/quast/report.tsv'
    wildcard_constraints:
        scenario='clean|adapter|quality|combined',
        action='raw|fastp_default|explicit_adapter|quality_trim|adapter_quality'
    params:
        output_dir=lambda wc: f'results/challenges/{wc.scenario}/{wc.action}/quast'
    threads: THREADS
    log: 'logs/agora_quast_{scenario}_{action}.log'
    shell:
        r"""
        mkdir -p logs
        quast.py {input:q} --threads {threads} -o {params.output_dir:q} > {log:q} 2>&1
        """

rule agora_challenge_profile:
    input:
        r1=lambda wc: agora_assembly_input(wc, 'R1'),
        r2=lambda wc: agora_assembly_input(wc, 'R2'),
        quast='results/challenges/{scenario}/{action}/quast/report.tsv'
    output:
        'results/challenges/{scenario}/{action}/profile.json'
    wildcard_constraints:
        scenario='clean|adapter|quality|combined',
        action='raw|fastp_default|explicit_adapter|quality_trim|adapter_quality'
    params:
        prior=CHALLENGE_GENOME_PRIOR
    log: 'logs/agora_profile_{scenario}_{action}.log'
    shell:
        r"""
        mkdir -p logs
        python scripts/agora_profile.py --r1 {input.r1:q} --r2 {input.r2:q} \
          --quast {input.quast:q} --genome-prior {params.prior} \
          --output {output:q} > {log:q} 2>&1
        """
