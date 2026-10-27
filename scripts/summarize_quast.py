#!/usr/bin/env python3
"""Produce a reference-free, machine-readable summary of two QUAST outputs."""

import argparse
import csv
import json
from pathlib import Path


FIELDS = {
    "# contigs": "contig_count",
    "Largest contig": "largest_contig_bp",
    "Total length": "assembly_length_bp",
    "N50": "n50_bp",
    "L50": "l50",
    "GC (%)": "gc_percent",
}


def number(value):
    if value in ("", "-", "NA", "None", None):
        return None
    cleaned = str(value).replace(",", "").strip().rstrip("%")
    try:
        x = float(cleaned)
    except ValueError:
        return None
    return int(x) if x.is_integer() else x


def parse_quast(path):
    with open(path, encoding="utf-8") as handle:
        rows = csv.reader(handle, delimiter="\t")
        header = next(rows, None)
        if not header or len(header) < 2:
            raise ValueError(f"QUAST TSV has no assembly column: {path}")
        result = {field: None for field in FIELDS.values()}
        result["assembly_name"] = header[1]
        for row in rows:
            if len(row) >= 2 and row[0] in FIELDS:
                result[FIELDS[row[0]]] = number(row[1])
        if result["n50_bp"] is None:
            raise ValueError(f"Missing N50 in QUAST report: {path}")
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True)
    parser.add_argument("--trimmed", required=True)
    parser.add_argument("--fastp", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with open(args.fastp, encoding="utf-8") as handle:
        fastp = json.load(handle)
    result = {
        "note": "reference-free QC only; neither a recovery score nor a scientific result",
        "raw": parse_quast(args.raw),
        "trimmed": parse_quast(args.trimmed),
        "fastp": {
            "before_filtering": fastp.get("summary", {}).get("before_filtering", {}),
            "after_filtering": fastp.get("summary", {}).get("after_filtering", {}),
            "adapter_cutting": fastp.get("adapter_cutting", {}),
            "filtering_result": fastp.get("filtering_result", {}),
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
