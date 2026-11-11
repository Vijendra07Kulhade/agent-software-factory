# Intake connector and Beads decision (first slice)

## Target boundary

`cron → source collector → normalized source revision → durable intake store/outbox → triage dispatcher → triage agent`.

`agents/connector.py` and `tools/intake_store.py` now implement only the offline collector/store boundary. A source adapter yields complete pages of normalized ticket records. `CollectorAgent.run` validates them and invokes the store to commit unique source revisions, the current work-item snapshot, an outbox record, and the caller-supplied safe cursor in one SQLite transaction. A failed page or malformed record leaves cursor and records unchanged. Duplicate revisions do not emit another triage event. This is a local test seam, not a GitHub/Jira API connector or a running agent; there is no cron registration, event delivery, triage worker, or multi-process claim/lease yet. The caller must derive a correct next cursor from a completely paginated source response; this has not been implemented.

Only an authorized dispatcher should claim outbox events and wake the triage agent with `(source, external_id, revision)`. It must fetch that immutable revision, not merely the latest mutable work item; enforce single claim, ack/retry and stale-revision policy before production. Ticket content is untrusted data and never executable instructions.

## Beads evaluation

Beads is a plausible **work-item graph and agent task board**, not automatically the entire intake transaction boundary. Its current upstream docs describe Dolt storage (embedded single-writer or server for concurrent writers), `external_ref` and `metadata` on issues, CLI/MCP access, and built-in GitHub/Jira pull sync. Do not assume an older SQLite-based Beads architecture. Sources: https://github.com/gastownhall/beads/blob/main/README.md ; https://github.com/gastownhall/beads/blob/main/docs/architecture/index.md ; https://github.com/gastownhall/beads/blob/main/docs/reference/faq.md .

Recommendation: **pilot Beads as the downstream agent-visible work-item view**, with external GitHub/Jira IDs in `external_ref` and source revision/provenance in metadata. Keep an intake ledger and transactional cursor/outbox outside Beads until a spike proves equivalent guarantees (atomic issue + cursor + wake-up event, idempotent revision updates, recovery after partial sync, concurrent collectors, sensitive-data handling and immutable revision history). Beads `bd github sync --pull-only` and `bd jira sync --pull` may replace source adapters in a pilot, but test their exact revision and failure behavior first; bidirectional sync must not be enabled by accident. Decide whether Beads or the ticket system is authoritative for each field; avoid an uncontrolled two-way synchronization loop.

This environment has no `bd` executable and no Beads workspace was initialized. No Beads API or CLI integration has been exercised. The local SQLite store is a deliberately replaceable prototype, not a decision against Beads. For multiple collectors on one shared Beads installation, assess server mode; embedded mode is single-writer. Do not treat `.beads/issues.jsonl` as the primary database or a full backup.

## Next verification gates

1. Build real GitHub/Jira read-only adapters with bounded pagination, comments/linkages mapping, source-provided revision/cursor and rate-limit handling.
2. Build outbox dispatcher with lease, ack/retry and immutable revision fetch; test crash and repeated delivery.
3. Spike `bd` in an isolated scratch repository with two external revisions, retry after interrupted pull, duplicate polls, and concurrent source collectors. Compare resulting work items and cursor/outbox against the ledger.
4. Select the Beads mapping/ownership model and only then enable a scheduled job in a test project.

The prior synthetic incident-repair demo has been removed from this working tree at the user's request. It is not the target SDLC. Any future evaluation/security controls must be designed and tested for the ticket-driven workflow rather than assumed to survive that removal.
