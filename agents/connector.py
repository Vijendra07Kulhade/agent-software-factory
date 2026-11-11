"""Offline collector agent: fetch complete source pages and invoke the intake store.

No external APIs or scheduler are wired; an adapter provides normalized pages.
"""
from tools.intake_store import IntakeStore


class CollectorAgent:
    """Owns intake only; triage workers claim outbox events separately."""
    def __init__(self, store: IntakeStore):
        self.store = store

    def run(self, adapter, scope: str, next_cursor: str) -> int:
        if adapter.source not in ("github", "jira") or not scope or not next_cursor:
            raise ValueError("unsupported source, scope, or cursor")
        # Materialize all pages before any write, so incomplete pagination fails closed.
        pages = list(adapter.fetch(self.store.cursor(adapter.source, scope)))
        records = [record for page in pages for record in page]
        for record in records:
            required = ("external_id", "revision", "title", "description", "source_url", "project", "status", "updated_at")
            if not isinstance(record, dict) or any(not isinstance(record.get(k), str) or not record[k] for k in required):
                raise ValueError("invalid source record")
            if not isinstance(record.get("labels"), list) or any(not isinstance(x, str) for x in record["labels"]):
                raise ValueError("invalid labels")
        return self.store.persist(adapter.source, scope, records, next_cursor)
