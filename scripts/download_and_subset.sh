#!/usr/bin/env bash
set -euo pipefail

mkdir -p data/raw data/subset data/tmp logs

if [[ ! -s data/raw/ERR008613_1.fastq || ! -s data/raw/ERR008613_2.fastq ]]; then
    echo "Downloading and extracting ERR008613 (may require >20 GB free disk)..."
    fasterq-dump ERR008613 --split-files -e 4 -O data/raw -t data/tmp
else
    echo "Reusing existing raw FASTQ files"
fi

echo "Sampling 1,200,000 matched pairs with seed 42..."
seqtk sample -s42 data/raw/ERR008613_1.fastq 1200000 | pigz -p 4 > data/subset/ecoli_R1.fastq.gz
seqtk sample -s42 data/raw/ERR008613_2.fastq 1200000 | pigz -p 4 > data/subset/ecoli_R2.fastq.gz
python scripts/verify_pairs.py data/subset/ecoli_R1.fastq.gz data/subset/ecoli_R2.fastq.gz --max-pairs 20000

echo "Dataset ready: data/subset/ecoli_R{1,2}.fastq.gz"
