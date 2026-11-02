"""Offline tests for SoCLaaS migration: no credentials, network, SPAdes required."""
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from soclaas_client import chat_json, parse_json_object
from agora_decide import decide
from agora_controller import experiment
from agora_profile import validate_profile


class DummyCompletions:
    def __init__(self, message):
        self.content = message
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason='stop', message=SimpleNamespace(content=self.content))])


class SoclaasTests(unittest.TestCase):
    def test_valid_json_and_code_fences(self):
        self.assertEqual(parse_json_object('{"action":"stop"}'), {'action': 'stop'})
        self.assertEqual(parse_json_object('```json\n{"action":"stop"}\n```'), {'action': 'stop'})

    def test_reject_invalid_json_or_extra_text(self):
        for message in ('Sure! {"action":"stop"}', '[1,2]', '', '{invalid}', '```json\n{}'):
            with self.subTest(message=message):
                with self.assertRaises(ValueError):
                    parse_json_object(message)

    def test_chat_uses_openai_compatible_endpoint_contract(self):
        d = DummyCompletions('{"action":"stop"}')
        client = SimpleNamespace(chat=SimpleNamespace(completions=d))
        out = chat_json(model='example-chat-model', messages=[{'role':'user','content':'test'}], client=client)
        self.assertEqual(out['action'], 'stop')
        self.assertEqual(d.requests[0]['model'], 'example-chat-model')
        self.assertNotIn('response_format', d.requests[0])

    def test_action_whitelist_applies_after_llm(self):
        p = {
            'schema_version': 'agora.challenge.v1',
            'read_qc': dict(read_pairs=200, total_bases=40000, mean_read_length_bp=100,
                            q20_percent=90, q30_percent=85, gc_percent=50, n_percent=0),
            'assembly_qc': dict(contig_count=50, largest_contig_bp=60000,
                                assembly_length_bp=100000, gc_percent=50, n50_bp=10000, l50=5),
            'coverage_estimate': dict(estimated_x=8, expected_genome_size_prior_bp=4600000),
            'artifact_signals': dict(adapter_motif_end_percent=10,
                                     tail_bases_below_q20_percent=40,
                                     qualification='Read-derived heuristics'),
        }
        validate_profile(p)
        sample = {'diagnosis':'mixed_signal','confidence':0.7,'action':'adapter_quality','reasoning':'Both signatures elevated.'}
        with patch('soclaas_client.chat_json',return_value=sample) as request:
            output = decide('llm',p,[],model='test-chat-model')
            self.assertEqual(output['action'],'adapter_quality')
            serialized = json.dumps(request.call_args.kwargs['messages'])
            self.assertNotIn('benchmark_metadata',serialized)
            self.assertNotIn('NGA50',serialized)
            self.assertNotIn('combined/',serialized)
        with patch('soclaas_client.chat_json',return_value={**sample,'action':'rm -rf /'}):
            with self.assertRaises(ValueError):
                decide('llm',p,[],model='test-chat-model')
        with patch('soclaas_client.chat_json',return_value={**sample,'benchmark_metadata':{'scenario':'combined'}}):
            with self.assertRaises(ValueError):
                decide('llm',p,[],model='test-chat-model')

    def test_model_required_for_llm_controller(self):
        with self.assertRaisesRegex(ValueError,'--model'):
            experiment('combined','llm',execute=True,model=None)
        plan = experiment('combined','llm',execute=False)
        self.assertIn('dry_plan',plan)


if __name__ == '__main__':
    unittest.main()
