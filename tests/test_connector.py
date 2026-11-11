import tempfile
import unittest
from pathlib import Path

from factory.connector import IntakeStore, CollectorAgent


class FakeSource:
    source = "github"
    def __init__(self, pages, fail_at=None):
        self.pages, self.fail_at = pages, fail_at
    def fetch(self, cursor):
        for index, page in enumerate(self.pages):
            if index == self.fail_at:
                raise RuntimeError("incomplete pagination")
            yield page


def ticket(revision="r1", title="Fix issue"):
    return {"external_id": "owner/repo#42", "revision": revision, "title": title,
            "description": "Expected X, saw Y", "source_url": "https://github.com/owner/repo/issues/42",
            "project": "owner/repo", "status": "open", "updated_at": "2026-01-01T00:00:00Z",
            "labels": ["bug"]}


class ConnectorTests(unittest.TestCase):
    def test_replay_and_revision_change_emit_once_per_revision(self):
        with tempfile.TemporaryDirectory() as root:
            store = IntakeStore(Path(root) / "intake.db")
            agent = CollectorAgent(store)
            source = FakeSource([[ticket()]])
            self.assertEqual(1, agent.run(source, "repo-scope", "page-end"))
            self.assertEqual(0, agent.run(source, "repo-scope", "page-end"))
            self.assertEqual(1, agent.run(FakeSource([[ticket("r2", "New title")]]), "repo-scope", "later"))
            events = store.pending_events()
            self.assertEqual(["r1", "r2"], [e["revision"] for e in events])
            self.assertEqual("later", store.cursor("github", "repo-scope"))
            self.assertEqual("New title", store.work_item("github", "owner/repo#42")["title"])
            store.close()

    def test_overlap_does_not_restore_old_revision_as_current(self):
        with tempfile.TemporaryDirectory() as root:
            store = IntakeStore(Path(root) / "intake.db")
            agent = CollectorAgent(store)
            agent.run(FakeSource([[ticket("r1")]]), "repo-scope", "a")
            agent.run(FakeSource([[ticket("r2", "Latest")]]), "repo-scope", "b")
            self.assertEqual(0, agent.run(FakeSource([[ticket("r1")]]), "repo-scope", "c"))
            self.assertEqual("Latest", store.work_item("github", "owner/repo#42")["title"])
            store.close()

    def test_partial_pages_do_not_commit_cursor_or_events(self):
        with tempfile.TemporaryDirectory() as root:
            store = IntakeStore(Path(root) / "intake.db")
            agent = CollectorAgent(store)
            with self.assertRaisesRegex(RuntimeError, "incomplete pagination"):
                agent.run(FakeSource([[ticket()], [ticket("r2")]], fail_at=1), "repo-scope", "end")
            self.assertIsNone(store.cursor("github", "repo-scope"))
            self.assertEqual([], store.pending_events())
            self.assertEqual(2, agent.run(FakeSource([[ticket()], [ticket("r2")]]), "repo-scope", "end"))
            store.close()

    def test_bad_record_fails_closed_without_side_effects(self):
        with tempfile.TemporaryDirectory() as root:
            store = IntakeStore(Path(root) / "intake.db")
            bad = ticket()
            bad["revision"] = ""
            with self.assertRaises(ValueError):
                CollectorAgent(store).run(FakeSource([[ticket(), bad]]), "repo-scope", "end")
            self.assertEqual([], store.pending_events())
            self.assertIsNone(store.cursor("github", "repo-scope"))
            store.close()


if __name__ == "__main__":
    unittest.main()
