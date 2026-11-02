import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from agora_holdout import prepare, validate_workspace, workspace_path


class HoldoutTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.root = Path(self.t.name)
        (self.root / 'scripts').mkdir()
        (self.root / 'workflow').mkdir()
        (self.root / 'results/trimmed/reads').mkdir(parents=True)
        (self.root / 'results/trimmed/fastp').mkdir(parents=True)
        (self.root / 'results/trimmed/fastp/fastp.json').write_text('{}')
        (self.root / 'results/trimmed/fastp/fastp.html').write_text('<html></html>')
        (self.root / 'Snakefile').write_text('include: "workflow/agora_challenge.smk"\n')
        (self.root / 'config.yaml').write_text('threads: 4\n')
        (self.root / 'scripts/agora_controller.py').write_text('print("controller")\n')
        (self.root / 'scripts/agora_inject.py').write_text('print("inject")\n')
        (self.root / 'scripts/agora_evaluate.py').write_text('print("evaluate")\n')
        (self.root / 'workflow/agora_challenge.smk').write_text('# challenge\n')
        for mate in ('R1','R2'):
            (self.root / f'results/trimmed/reads/{mate}.fastq.gz').write_bytes(b'fake gz')

    def tearDown(self):
        self.t.cleanup()

    def test_prepare_has_unique_seed_and_snapshot(self):
        work = prepare(self.root, 3101)
        self.assertEqual(work, workspace_path(self.root, 3101))
        self.assertTrue((work / 'results/trimmed/reads/R1.fastq.gz').is_file())
        self.assertEqual(validate_workspace(self.root, 3101), work)
        self.assertEqual(json.loads((work/'holdout_manifest.json').read_text())['seed'], 3101)
        self.assertIn('seed: 3101', (work/'config.yaml').read_text())

    def test_cannot_override_completed_workspace(self):
        prepare(self.root, 3101)
        with self.assertRaises(FileExistsError):
            prepare(self.root, 3101)

    def test_dev_seed_rejected(self):
        with self.assertRaises(ValueError):
            prepare(self.root, 2026)

    def test_modified_snapshot_rejected(self):
        work = prepare(self.root, 3101)
        (work/'scripts/agora_inject.py').write_text('modified')
        with self.assertRaises(ValueError):
            validate_workspace(self.root, 3101)


if __name__ == '__main__':
    unittest.main()
