import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_agent_profile import build_profile, read_pair_stats, read_quast


class AgentProfileTests(unittest.TestCase):
    def test_profile_does_not_leak_reference_or_failure_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a = root / "R1.fastq.gz"
            b = root / "R2.fastq.gz"
            for path, suffix, seq in ((a, "1", "ACGT"), (b, "2", "GGNN")):
                with gzip.open(path, "wt", encoding="ascii") as stream:
                    stream.write(f"@pairA/{suffix}\n{seq}\n+\nIIII\n")
            quast = root / "report.tsv"
            quast.write_text("Assembly\tcontigs\n# contigs\t12\nLargest contig\t400\n"
                             "Total length\t500\nN50\t150\nL50\t2\nGC (%)\t50.0\n"
                             "Genome fraction (%)\t99.9\n# misassemblies\t7\n"
                             "Reference length\t1234567\n", encoding="utf-8")
            profile = build_profile(a, b, quast, 400)
            self.assertEqual(profile["read_qc"]["total_bases"], 8)
            self.assertEqual(profile["read_qc"]["read_pairs"], 1)
            self.assertEqual(profile["read_qc"]["q30_percent"], 100)
            self.assertEqual(profile["coverage_estimate"]["estimated_x"], 0.02)
            encoded = json.dumps(profile).lower()
            for forbidden in ("benchmark_metadata", "scenario", "genome fraction", "misassemblies", "reference length", "99.9", "1234567"):
                self.assertNotIn(forbidden, encoded)

    def test_mate_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = [Path(temp) / "r1.fastq.gz", Path(temp) / "r2.fastq.gz"]
            for i, path in enumerate(paths):
                with gzip.open(path, "wt", encoding="ascii") as stream:
                    stream.write(f"@pair{i}/1\nAAAA\n+\nIIII\n")
            with self.assertRaises(ValueError):
                read_pair_stats(*paths)


if __name__ == "__main__":
    unittest.main()
