import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "cron-job"
SPEC = importlib.util.spec_from_file_location("cron_validator", SKILL / "scripts" / "validate_job.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CronJobContractTests(unittest.TestCase):
    def setUp(self):
        self.job = json.loads((SKILL / "templates" / "job.example.json").read_text())

    def test_draft_example_validates(self):
        self.assertEqual([], MODULE.validate(self.job))

    def test_rejects_missing_durable_state(self):
        self.job["state"].pop("cursor_store")
        self.assertTrue(MODULE.validate(self.job))

    def test_rejects_privileged_collector(self):
        self.job["permissions"]["deploy"] = True
        self.assertTrue(MODULE.validate(self.job))

    def test_rejects_inline_credential(self):
        self.job["credentials"]["token"] = "not-a-secret"
        self.assertTrue(MODULE.validate(self.job))

    def test_approved_job_requires_resolved_fields(self):
        self.job["status"] = "approved"
        self.assertTrue(MODULE.validate(self.job))

    def test_requires_five_fields_and_utc(self):
        for expression in ("0 0 * *", "0 0 * * * *"):
            with self.subTest(expression=expression):
                job = copy.deepcopy(self.job)
                job["schedule"]["cron"] = expression
                self.assertTrue(MODULE.validate(job))
        self.job["schedule"]["timezone"] = "local"
        self.assertTrue(MODULE.validate(self.job))


if __name__ == "__main__":
    unittest.main()
