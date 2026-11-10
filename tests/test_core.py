import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / 'examples/baseline'


class FactoryTests(unittest.TestCase):
    def test_roas_vertical_demo_reproduces_then_fixes(self):
        self.assertTrue((PROJECT / 'factory/core.py').exists(), 'factory core is not implemented')
        from factory.core import run_incident, source_digest, PATCHABLE_PATHS
        before = source_digest(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'result'
            report = run_incident(ROOT, PROJECT / 'examples/incidents/roas-unit-mismatch.json', out)
            self.assertEqual(report['status'], 'ready_for_review')
            self.assertTrue(report['fixture_mode'])
            self.assertFalse(report['evaluation']['baseline_passed'])
            self.assertTrue(report['evaluation']['candidate_passed'])
            self.assertEqual(source_digest(ROOT), before)
            self.assertEqual(source_digest(out / 'candidate'), report['candidate_content_hash'])
            for name in ['report.json', 'report.md', 'candidate.patch', 'pr-body.md']:
                self.assertTrue((out / name).is_file())
            self.assertTrue(set(report['changed_paths']) <= set(PATCHABLE_PATHS))
            self.assertEqual(json.loads((out / 'report.json').read_text()), report)

    def test_campaign_contract_fix(self):
        from factory.core import run_incident
        fixture = PROJECT / 'examples/incidents/campaign-confirmation.json'
        self.assertTrue(fixture.exists(), 'campaign vertical slice missing')
        with tempfile.TemporaryDirectory() as tmp:
            report = run_incident(ROOT, fixture, Path(tmp) / 'out')
            self.assertEqual(report['status'], 'ready_for_review')
            self.assertEqual(report['diagnosis']['classification'], 'skill_contract_defect')
            self.assertFalse(report['evaluation']['baseline_passed'])
            self.assertTrue(report['evaluation']['candidate_passed'])
            self.assertTrue(all(c['kind'] == 'static_skill_contract' for c in report['evaluation']['cases']['candidate']))
            self.assertIn('not LLM behavioral proof', report['diagnosis']['explanation'])

    def test_evidence_gates_and_timeout(self):
        from factory.core import run_incident
        raw = json.loads((PROJECT / 'examples/incidents/roas-unit-mismatch.json').read_text())
        self.assertIn('events', raw, 'normalized joined evidence not implemented')
        mutations = [
            ('tenant', 'different-tenant'), ('release', 'wrong-release'),
            ('agent', 'Reporting-Agent'), ('skill_version', 'wrong-skill-version'),
            ('source_hash', '0' * 64), ('timestamp', '2026-10-21T10:30:00Z'),
            ('trace_id', 'other-trace'), ('correlation_id', 'other-correlation'),
            ('signal', 'unknown_signal'),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for index, (key, value) in enumerate(mutations):
                with self.subTest(key=key):
                    data = json.loads(json.dumps(raw))
                    data['events'][2][key] = value
                    incident = Path(tmp) / 'incident.json'
                    incident.write_text(json.dumps(data))
                    report = run_incident(ROOT, incident, Path(tmp) / str(index))
                    self.assertEqual(report['status'], 'needs_human')
                    self.assertEqual(report['changed_paths'], [])
            report = run_incident(ROOT, PROJECT / 'examples/incidents/upstream-timeout.json', Path(tmp) / 'timeout')
            self.assertEqual(report['status'], 'needs_human')
            self.assertEqual(report['diagnosis']['classification'], 'upstream_failure')
            self.assertEqual(report['changed_paths'], [])

    def test_verification_rejects_tampering_and_stale_base(self):
        import factory.core as core
        import shutil
        self.assertTrue(hasattr(core, 'verify_bundle'), 'independent verification gate missing')
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            repo = tmp / 'repo'
            for name in core.INPUT_PATHS:
                (repo / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, repo / name)
            out = tmp / 'out'
            report = core.run_incident(repo, PROJECT / 'examples/incidents/roas-unit-mismatch.json', out)
            self.assertEqual(core.verify_bundle(repo, out), report)
            original_report = (out / 'report.json').read_text()
            candidate_file = out / 'candidate' / core.PATCHABLE_PATHS[0]
            original_source = candidate_file.read_text()
            # Even a rehashed extra side effect must fail before evaluator execution.
            candidate_file.write_text(original_source + '\nraise RuntimeError("tampered")\n')
            report['candidate_content_hash'] = core.source_digest(out / 'candidate')
            (out / 'report.json').write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                core.verify_bundle(repo, out)
            candidate_file.write_text(original_source)
            (out / 'report.json').write_text(original_report)
            for mutation in ({'changed_paths': ['../../secret']}, {'changed_paths': []}, {'status': 'needs_human'}, {'evaluation': {'baseline_passed': True, 'candidate_passed': True}}):
                bad = json.loads(original_report)
                bad.update(mutation)
                (out / 'report.json').write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    core.verify_bundle(repo, out)
            (out / 'report.json').write_text(original_report)
            extra = out / 'candidate/.env'
            extra.write_text('secret')
            with self.assertRaises(ValueError):
                core.verify_bundle(repo, out)
            extra.unlink()
            candidate_file.unlink()
            candidate_file.symlink_to(repo / core.PATCHABLE_PATHS[0])
            with self.assertRaises(ValueError):
                core.verify_bundle(repo, out)
            candidate_file.unlink()
            candidate_file.write_text(original_source)
            (repo / core.PATCHABLE_PATHS[2]).write_text('stale base')
            with self.assertRaises(ValueError):
                core.verify_bundle(repo, out)


if __name__ == '__main__':
    unittest.main()
