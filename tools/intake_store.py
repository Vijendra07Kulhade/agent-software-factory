"""Durable local intake ledger; no ticket API calls or agent reasoning."""
import json
import sqlite3
from pathlib import Path


class IntakeStore:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS cursors (
                source TEXT NOT NULL, scope TEXT NOT NULL, value TEXT NOT NULL,
                PRIMARY KEY(source, scope));
            CREATE TABLE IF NOT EXISTS revisions (
                source TEXT NOT NULL, external_id TEXT NOT NULL, revision TEXT NOT NULL,
                snapshot TEXT NOT NULL,
                PRIMARY KEY(source, external_id, revision));
            CREATE TABLE IF NOT EXISTS work_items (
                source TEXT NOT NULL, external_id TEXT NOT NULL, revision TEXT NOT NULL,
                snapshot TEXT NOT NULL, workflow_state TEXT NOT NULL DEFAULT 'discovered',
                PRIMARY KEY(source, external_id));
            CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
                external_id TEXT NOT NULL, revision TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0,
                UNIQUE(source, external_id, revision));
        """)

    def cursor(self, source, scope):
        row = self.db.execute("SELECT value FROM cursors WHERE source=? AND scope=?", (source, scope)).fetchone()
        return row[0] if row else None

    def pending_events(self):
        return [dict(zip(("id", "source", "external_id", "revision"), row)) for row in
                self.db.execute("SELECT id, source, external_id, revision FROM outbox WHERE delivered=0 ORDER BY id")]

    def work_item(self, source, external_id):
        row = self.db.execute("SELECT snapshot FROM work_items WHERE source=? AND external_id=?", (source, external_id)).fetchone()
        return json.loads(row[0]) if row else None

    def persist(self, source: str, scope: str, records: list[dict], next_cursor: str) -> int:
        """Commit revisions, current view, outbox and cursor in one transaction."""
        inserted = 0
        with self.db:
            for record in records:
                payload = json.dumps({"source": source, **record}, sort_keys=True)
                cur = self.db.execute(
                    "INSERT OR IGNORE INTO revisions VALUES (?, ?, ?, ?)",
                    (source, record["external_id"], record["revision"], payload))
                if cur.rowcount:
                    inserted += 1
                    self.db.execute(
                        "INSERT INTO work_items(source, external_id, revision, snapshot) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(source, external_id) DO UPDATE SET revision=excluded.revision, snapshot=excluded.snapshot, workflow_state='discovered'",
                        (source, record["external_id"], record["revision"], payload))
                    self.db.execute(
                        "INSERT INTO outbox(source, external_id, revision) VALUES (?, ?, ?)",
                        (source, record["external_id"], record["revision"]))
            self.db.execute(
                "INSERT INTO cursors VALUES (?, ?, ?) ON CONFLICT(source, scope) DO UPDATE SET value=excluded.value",
                (source, scope, next_cursor))
        return inserted

    def close(self):
        self.db.close()
