import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_demo_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            result = subprocess.run([sys.executable, '-m', 'factory', 'demo', '--scenario',
                                     'roas-unit-mismatch', '--out', str(out)], cwd=ROOT,
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'ready_for_review')
            verified = subprocess.run([sys.executable, '-m', 'factory', 'verify', '--bundle', str(out)],
                                      cwd=ROOT, capture_output=True, text=True, timeout=20)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertTrue(json.loads(verified.stdout)['verified'])

    def test_demo_keeps_frozen_baseline_after_workspace_fix(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / 'repo'
            shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns('.git', '__pycache__', 'artifacts'))
            out = Path(tmp) / 'first'
            command = [sys.executable, '-m', 'factory', 'demo', '--scenario', 'roas-unit-mismatch', '--out']
            first = subprocess.run(command + [str(out)], cwd=repo, capture_output=True, text=True, timeout=20)
            self.assertEqual(first.returncode, 0, first.stderr)
            relative = 'examples/agents/ads/roas.py'
            shutil.copyfile(out / 'candidate' / relative, repo / relative)
            second = subprocess.run(command + [str(Path(tmp) / 'second')], cwd=repo,
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(json.loads(second.stdout)['status'], 'ready_for_review')

    def test_timeout_is_successful_triage_not_a_verified_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            result = subprocess.run([sys.executable, '-m', 'factory', 'demo', '--scenario',
                                     'upstream-timeout', '--out', str(out)], cwd=ROOT,
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'needs_human')
            verified = subprocess.run([sys.executable, '-m', 'factory', 'verify', '--bundle', str(out)],
                                      cwd=ROOT, capture_output=True, text=True, timeout=20)
            self.assertNotEqual(verified.returncode, 0)


if __name__ == '__main__':
    unittest.main()
