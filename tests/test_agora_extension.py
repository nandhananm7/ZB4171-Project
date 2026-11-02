"""Offline unit tests; do not require SPAdes/fastp/OpenAI or an API key."""
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from agora_inject import generate, fastq_records
from agora_profile import profile, validate_profile
from agora_decide import rule_decide, mock_decide, decide
from agora_controller import path_for, acceptable, experiment


QUAST = ('Assembly\tcontigs\n# contigs\t100\nLargest contig\t20000\n'
         'Total length\t100000\nN50\t10000\nL50\t4\nGC (%)\t50.0\n'
         'NGA50\t9999\nGenome fraction (%)\t100\n')


def mkread(root, name, count=20):
    with gzip.open(root / name, 'wt') as f:
        for i in range(count):
            f.write(f'@read{i}/1\n'+ 'C'*65+'A'*35+'\n+\n'+'I'*100+'\n')


class AgoraTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        mkread(self.path, 'one.fastq.gz')
        with gzip.open(self.path / 'two.fastq.gz', 'wt') as f:
            for i in range(20):
                f.write(f'@read{i}/2\n'+'G'*100+'\n+\n'+'I'*100+'\n')
        (self.path/'report.tsv').write_text(QUAST)

    def test_injection_keeps_pairs_and_varies_bases(self):
        m = generate(self.path/'one.fastq.gz', self.path/'two.fastq.gz',
                     self.path/'corrupt1.gz', self.path/'corrupt2.gz',
                     self.path/'metadata.json', 'combined', seed=3, max_pairs=20,
                     adapter_rate=1.0, error_rate=0.0)
        self.assertEqual(m['read_pairs'],20)
        records = list(fastq_records(self.path/'corrupt1.gz'))
        self.assertEqual(len(records), 20)
        self.assertTrue(all('AGATCGGA' in r[1] for r in records))
        self.assertEqual(len(records[0][1]),len(records[0][3]))
        self.assertEqual(len(list(fastq_records(self.path/'corrupt2.gz'))),20)

    def test_profile_is_safe_and_detects_adapter(self):
        generate(self.path/'one.fastq.gz',self.path/'two.fastq.gz',
                 self.path/'corrupt1.gz',self.path/'corrupt2.gz',
                 self.path/'metadata.json','adapter',seed=1,max_pairs=20,
                 adapter_rate=1.0)
        p = profile(self.path/'corrupt1.gz',self.path/'corrupt2.gz',
                    self.path/'report.tsv', 100000)
        self.assertEqual(p['artifact_signals']['adapter_motif_end_percent'],100)
        self.assertNotIn('NGA50',json.dumps(p))
        self.assertNotIn('scenario',json.dumps(p))
        self.assertEqual(rule_decide(p,[])['action'],'fastp_default')
        p['benchmark_metadata']={'scenario':'adapter'}
        with self.assertRaises(ValueError):
            validate_profile(p)

    def test_reject_injected_reference_measurement(self):
        p = profile(self.path/'one.fastq.gz',self.path/'two.fastq.gz',
                    self.path/'report.tsv',100000)
        p['assembly_qc']['genome_fraction']=98
        with self.assertRaises(ValueError):
            validate_profile(p)

    def test_action_values_are_fixed(self):
        self.assertEqual(mock_decide({},[])['action'],'fastp_default')
        for a in ['../escape','rm -rf','foo']:
            with self.assertRaises(ValueError):
                path_for('combined',a)
        with self.assertRaises(ValueError):
            path_for('../clean','raw')

    def test_safety_guard_and_dry_plan(self):
        b = profile(self.path/'one.fastq.gz',self.path/'two.fastq.gz',
                    self.path/'report.tsv',100000)
        c = json.loads(json.dumps(b))
        c['assembly_qc']['assembly_length_bp'] = 75000
        accepted, reason = acceptable(b,c)
        self.assertFalse(accepted)
        plan = experiment('combined','mock',execute=False)
        self.assertEqual(len(plan['dry_plan']),2)
        self.assertTrue(all('combined' in x for x in plan['dry_plan']))

    def test_no_llm_in_offline_rule(self):
        p = profile(self.path/'one.fastq.gz',self.path/'two.fastq.gz',
                    self.path/'report.tsv',100000)
        decision = decide('rule',p,[],'unused')
        self.assertIn(decision['action'], ('stop', 'fastp_default', 'explicit_adapter','quality_trim','adapter_quality'))


if __name__ == '__main__':
    unittest.main()
