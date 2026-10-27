import importlib.util
from pathlib import Path
import unittest

FILE = Path(__file__).resolve().parents[1] / "scripts" / "rule_based_agent.py"
spec = importlib.util.spec_from_file_location("rule_based_agent", FILE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def profile(depth):
    return {
        "schema_version": "1.0",
        "read_qc": {"q30_percent": 84.905},
        "assembly_qc": {"n50_bp": 7681, "contig_count": 953},
        "coverage_estimate": {"estimated_x": depth},
    }


class AgentBaselineTests(unittest.TestCase):
    def test_8x_suspected_low_coverage(self):
        got = module.diagnose(profile(8.073))
        self.assertEqual(got["diagnosis"], "suspected_low_coverage")
        self.assertEqual(got["severity"], "severe")
        self.assertEqual(got["action"]["name"], "no_change")

    def test_15x_moderate_low_coverage(self):
        got = module.diagnose(profile(15.14))
        self.assertEqual(got["severity"], "moderate")

    def test_30x_no_strong_low_coverage_signal(self):
        got = module.diagnose(profile(30.3))
        self.assertEqual(got["diagnosis"], "no_strong_low_coverage_signal")

    def test_rejects_benchmark_label(self):
        bad = profile(8.073)
        bad["benchmark_metadata"] = {"scenario": "low_coverage"}
        with self.assertRaises(ValueError):
            module.diagnose(bad)

    def test_rejects_reference_measurement(self):
        bad = profile(8.073)
        bad["assembly_qc"]["genome_fraction"] = 96.618
        with self.assertRaises(ValueError):
            module.diagnose(bad)


if __name__ == "__main__":
    unittest.main()
