"""Milestone 9 offline unit tests: no SoCLaaS, no QUAST, no SPAdes."""
import json
import importlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from agora_feedback_ablation import (history_for, replay_selection,
                                     order_for_repetition, successful_records,
                                     run_calls, profile_file, evaluate)


def profile(n50=10000, contigs=100, tail=30, adapter=20):
    return {
        "schema_version": "agora.challenge.v1",
        "read_qc": {"read_pairs": 500, "total_bases": 100000,
                    "mean_read_length_bp": 100, "q20_percent": 90,
                    "q30_percent": 80, "gc_percent": 50, "n_percent": 0},
        "assembly_qc": {"contig_count": contigs, "largest_contig_bp": 20000,
                        "assembly_length_bp": 100000, "gc_percent": 50,
                        "n50_bp": n50, "l50": 4},
        "coverage_estimate": {"estimated_x": 20, "expected_genome_size_prior_bp": 5000},
        "artifact_signals": {"adapter_motif_end_percent": adapter,
                             "tail_bases_below_q20_percent": tail,
                             "qualification": "Heuristic only"},
    }


class FeedbackAblationTests(unittest.TestCase):
    def test_only_feedback_fields_change(self):
        baseline, trial = profile(), profile(n50=11500, contigs=90, tail=8, adapter=0.2)
        no = history_for("fastp_default", trial, baseline, "no_feedback")
        yes = history_for("fastp_default", trial, baseline, "feedback")
        self.assertEqual(no[0]["action"], yes[0]["action"])
        self.assertIsNone(no[0]["result"])
        self.assertIsNone(no[0]["acceptable"])
        self.assertIsNone(no[0]["explanation"])
        self.assertEqual(yes[0]["result"]["n50_bp"], 11500)
        self.assertTrue(yes[0]["acceptable"])
        self.assertNotIn("NGA50", json.dumps(yes))
        self.assertNotIn("reference", json.dumps(yes).lower())
        self.assertNotIn("scenario", json.dumps(yes).lower())

    def test_replay_stops_and_rejects_duplicate(self):
        base, first = profile(), profile(n50=11500, contigs=90)
        accepted = replay_selection(base, first, "fastp_default", "stop", None)
        self.assertEqual(accepted["selected"], "fastp_default")
        dup = replay_selection(base, first, "fastp_default", "fastp_default", first)
        self.assertEqual(dup["status"], "duplicate_action_violation")
        missing = replay_selection(base, first, "fastp_default", "adapter_quality", None)
        self.assertEqual(missing["status"], "missing_second_action_profile")
        self.assertEqual(missing["selected"], "fastp_default")

    def test_replay_replaces_only_if_better(self):
        base = profile()
        first = profile(n50=11000, contigs=97, tail=25, adapter=15)
        second = profile(n50=14000, contigs=75, tail=5, adapter=0)
        result = replay_selection(base, first, "fastp_default", "adapter_quality", second)
        self.assertEqual(result["status"], "evaluated")
        self.assertEqual(result["selected"], "adapter_quality")
        self.assertTrue(result["second_acceptable"])

    def test_randomized_order_has_exactly_two_arms(self):
        for i in range(1, 20):
            self.assertEqual(set(order_for_repetition(i, 91)), {"feedback", "no_feedback"})
            self.assertEqual(order_for_repetition(i, 91), order_for_repetition(i, 91))


    def test_evaluate_joins_only_posthoc_benchmark(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src = Path(__file__).resolve().parents[1] / "scripts"
            scriptdir = root / "scripts"
            scriptdir.mkdir()
            for name in ("agora_feedback_ablation.py", "agora_controller.py",
                         "agora_decide.py", "agora_profile.py", "soclaas_client.py"):
                shutil.copyfile((src / name) if (src / name).is_file() else Path(importlib.import_module(name[:-3]).__file__), scriptdir / name)
            wk = root / "results" / "holdouts" / "seed_3101"
            base, first, second = profile(), profile(n50=11500, contigs=90), profile(n50=14000, contigs=75)
            for action, p in (("raw", base), ("fastp_default", first), ("adapter_quality", second)):
                pp = profile_file(wk, "adapter", action)
                pp.parent.mkdir(parents=True, exist_ok=True)
                pp.write_text(json.dumps(p))
                fa = pp.parent / "spades" / "contigs.fasta"
                fa.parent.mkdir(parents=True)
                fa.write_text(">ctg\n" + "A"*100 + "\n")
            def fake_decide(backend, p, history, model, baseline):
                return {"diagnosis": "mixed_signal", "confidence": 0.8,
                        "action": "adapter_quality" if history[0]["result"] is None else "stop",
                        "reasoning": "Mock"}
            with patch("agora_feedback_ablation.decide", side_effect=fake_decide):
                run_calls(root, 3101, "adapter", "fastp_default", "dummy", 1, 91)
            def fake_quast(root, seed, scenario, first, model, reference, threads, needed):
                self.assertEqual(needed, {"raw", "fastp_default", "adapter_quality"})
                self.assertEqual(reference.read_text(), ">ref\nAAAA\n")
                return {"variants": sorted(needed), "metrics": {
                    "NGA50": {"raw": "10000", "fastp_default": "11500", "adapter_quality": "14000"},
                    "# mismatches per 100 kbp": {"raw": "4.0", "fastp_default": "3.0", "adapter_quality": "2.0"}},
                    "note": "BENCHMARK ONLY"}
            ref = root / "ref.fasta"
            ref.write_text(">ref\nAAAA\n")
            with patch("agora_feedback_ablation.benchmark_quast", side_effect=fake_quast):
                out = evaluate(root, 3101, "adapter", "fastp_default", "dummy", 1, 91, ref, 2)
            summary = json.loads((out / "summary.json").read_text())
            self.assertEqual(summary["complete_pairs"], 1)
            self.assertEqual(summary["fully_benchmarked_pairs"], 1)
            self.assertEqual(summary["median_paired_nga50_delta_bp"], -2500.0)
            self.assertEqual(summary["median_paired_mismatch_delta"], 1.0)
            self.assertTrue((out / "REPORT.md").is_file())
            with (out / "paired_decisions.csv").open() as f:
                csvtext = f.read()
            self.assertIn("no_feedback", csvtext)
            self.assertIn("feedback", csvtext)

    def test_run_resumes_and_profile_constant(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src = Path(__file__).resolve().parents[1] / "scripts"
            scriptdir = root / "scripts"
            scriptdir.mkdir()
            for name in ("agora_feedback_ablation.py", "agora_controller.py",
                         "agora_decide.py", "agora_profile.py", "soclaas_client.py"):
                shutil.copyfile((src / name) if (src / name).is_file() else Path(importlib.import_module(name[:-3]).__file__), scriptdir / name)
            wk = root / "results" / "holdouts" / "seed_3101"
            baseline = profile()
            trial = profile(n50=11500, contigs=90, tail=8, adapter=0)
            for action, p in (("raw", baseline), ("fastp_default", trial)):
                path = profile_file(wk, "adapter", action)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(p))
            seen = []

            def fake_decide(backend, p, history, model, baseline_observation):
                seen.append((p, baseline_observation, history))
                return {"diagnosis": "mixed_signal", "confidence": 0.9,
                        "action": "stop" if history[0]["result"] else "adapter_quality",
                        "reasoning": "Mock decision"}

            with patch("agora_feedback_ablation.decide", side_effect=fake_decide):
                path = run_calls(root, 3101, "adapter", "fastp_default", "dummy", 2, 91)
                self.assertEqual(len(seen), 4)
                self.assertEqual(seen[0][0], seen[1][0])
                self.assertEqual(seen[0][0], baseline)
                self.assertNotIn("NGA50", json.dumps(seen))
                self.assertEqual(len(successful_records(path / "decisions.jsonl", 2)), 4)
                run_calls(root, 3101, "adapter", "fastp_default", "dummy", 2, 91)
                self.assertEqual(len(seen), 4, "Completed calls must be skipped")


if __name__ == "__main__":
    unittest.main()
