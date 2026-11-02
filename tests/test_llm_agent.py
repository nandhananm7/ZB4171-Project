"""Offline checks for AGORA LLM client integration (no API key or network)."""
from __future__ import annotations
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "llm_agent.py"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("llm_agent", MODULE_PATH)
agent = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = agent
spec.loader.exec_module(agent)

PROFILE = {
    "schema_version": "1.0",
    "read_qc": {"read_pairs":185700,"total_bases":37133894,"mean_read_length_bp":99.984,
                "q20_percent":92.68,"q30_percent":84.905,"gc_percent":50.299,"n_percent":0.0633},
    "assembly_qc": {"contig_count":953,"largest_contig_bp":32298,"assembly_length_bp":4490786,
                    "gc_percent":50.68,"n50_bp":7681,"l50":186},
    "coverage_estimate": {"estimated_x":8.073,"method":"sequenced_bases / approximate_expected_genome_size",
                          "expected_genome_size_prior_bp":4600000,
                          "qualification":"Approximate nominal depth, not a measured depth."},
}

class LLMTests(unittest.TestCase):
    def test_agent_safe_profile_accepted(self):
        self.assertEqual(agent.safe_profile(PROFILE)["coverage_estimate"]["estimated_x"],8.073)

    def test_restricted_reference_field_rejected(self):
        p = json.loads(json.dumps(PROFILE))
        p["assembly_qc"]["nga50"] = 7117
        with self.assertRaises(ValueError):
            agent.safe_profile(p)

    def test_restricted_label_rejected(self):
        p = json.loads(json.dumps(PROFILE))
        p["benchmark_metadata"] = {"scenario":"low_coverage"}
        with self.assertRaises(ValueError):
            agent.safe_profile(p)

    def test_action_always_maps_to_fixed_parameters(self):
        d = agent.ModelDecision(diagnosis="suspected_low_coverage", severity="severe", confidence=.8,
                                evidence=["coverage 8"], reasoning="Low depth likely", action="short_k",
                                action_reasoning="Experiment only", limitations=["prior-dependent"])
        out = agent.build_decision(PROFILE, d, "gpt-5-mini")
        self.assertEqual(out["action"],{"name":"short_k","parameters":{"k":"21,33"}})
        self.assertFalse(out["executed"])

    def test_unapproved_action_rejected(self):
        with self.assertRaises(Exception):
            agent.ModelDecision(diagnosis="uncertain", severity="not_assigned",confidence=.2,
                                evidence=["data"], reasoning="unknown", action="run_shell",
                                action_reasoning="x",limitations=[])

    def test_client_receives_only_profile_json(self):
        seen = {}
        decision = agent.ModelDecision(diagnosis="suspected_low_coverage",severity="moderate", confidence=.75,
                                       evidence=["evidence"],reasoning="reasoning",action="no_change",
                                       action_reasoning="no evidence for repair",limitations=[])
        class DummyCompletions:
            def create(self, **kwargs):
                seen.update(kwargs)
                return SimpleNamespace(choices=[SimpleNamespace(
                    finish_reason="stop", message=SimpleNamespace(content=decision.model_dump_json()))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=DummyCompletions()))
        agent.get_prediction(PROFILE,"sample-chat-model",client)
        payload = seen["messages"][1]["content"]
        self.assertIn("coverage_estimate",payload)
        self.assertNotIn("benchmark_metadata",payload)
        self.assertNotIn("results/agent_profiles/8x",payload)

if __name__ == "__main__":
    unittest.main()
