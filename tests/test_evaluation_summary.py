"""Small offline tests for cross-scenario summary. No SPAdes, keys, or internet."""
import csv
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'agora_summary.py'
spec = importlib.util.spec_from_file_location('agora_summary', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        folder = self.root / 'results/evaluation/challenges/combined'
        folder.mkdir(parents=True)
        metrics = {
            '# contigs': {'raw': '133', 'fastp_default': '122', 'llm_iterative': '121'},
            'N50': {'raw': '71994', 'fastp_default': '78664', 'llm_iterative': '77603'},
            'NGA50': {'raw': '69548', 'fastp_default': '78605', 'llm_iterative': '71349'},
            'Genome fraction (%)': {'raw': '98.073', 'fastp_default': '98.077', 'llm_iterative': '98.105'},
            '# misassemblies': {'raw': '1', 'fastp_default': '1', 'llm_iterative': '2'},
            '# mismatches per 100 kbp': {'raw': '4.37', 'fastp_default': '4.99', 'llm_iterative': '3.29'},
            '# indels per 100 kbp': {'raw': '1.25', 'fastp_default': '1.12', 'llm_iterative': '0.97'},
        }
        (folder / 'comparison.json').write_text(json.dumps({'strategies': ['raw', 'fastp_default', 'llm_iterative'], 'metrics': metrics}))
        audit = self.root / 'results/agent_runs/combined/llm_iterative.json'
        audit.parent.mkdir(parents=True)
        audit.write_text(json.dumps({
            'selected_action': 'adapter_quality', 'model': 'qwen3.8:27b',
            'decisions': [{'diagnosis': 'mixed_signal', 'action': 'adapter_quality', 'reasoning': 'Both issues'},
                          {'diagnosis': 'no_strong_signal', 'action': 'stop'}],
            'attempts': [{'action': 'adapter_quality', 'acceptable': True}]
        }))
        os.utime(audit, (folder.joinpath('comparison.json').stat().st_mtime + 10,) * 2)

    def test_metrics_join_and_diagnosis(self):
        rows, decisions, warnings = mod.calculate(self.root)
        llm = next(r for r in rows if r['scenario'] == 'combined' and r['strategy'] == 'llm_iterative')
        self.assertEqual(llm['selected_action'], 'adapter_quality')
        self.assertEqual(llm['diagnosis_category_match'], 'yes')
        self.assertEqual(llm['repair_attempts'], 1)
        self.assertEqual(llm['accepted_attempts'], 1)
        self.assertEqual(llm['nga50_bp'], 71349)
        self.assertAlmostEqual(llm['mismatch_change_vs_fastp_per_100kb'], -1.70)
        self.assertEqual(len(decisions), 1)
        self.assertTrue(any('STALE' in x for x in warnings))

    def test_creates_csv_markdown_and_handles_missing_files(self):
        mod.generate(self.root, self.root / 'summary')
        with (self.root / 'summary/agora_comparison.csv').open(newline='') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 3)
        report = (self.root / 'summary/AGORA_Cross_Scenario_Report.md').read_text()
        self.assertIn('Combined scenario', report)
        self.assertIn('BENCHMARK', report.upper())
        self.assertIn('qwen3.8', (self.root / 'summary/agent_decisions.csv').read_text())

    def test_number_handling(self):
        self.assertEqual(mod.number('1,234'), 1234)
        self.assertIsNone(mod.number('-'))
        self.assertIsNone(mod.number('NaN'))


if __name__ == '__main__':
    unittest.main()
