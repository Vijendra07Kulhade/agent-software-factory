# Agent Software Factory

A ticket-driven software factory under development. The intended SDLC is intake → triage → specification → implementation → verification → review → feedback, with human approval and a separate release/rollback handoff. See `Agent.md` and `docs/TICKET_DRIVEN_FACTORY_PROPOSAL.md` for the target architecture.

## What works now

- `agents/connector.py`: an offline collector agent that accepts normalized, paginated source records through an injected adapter, validates them, and delegates persistence. No live GitHub/Jira calls occur.
- `skills/cron-job/SKILL.md`: a harness-agnostic procedure for authoring scheduled jobs, with a draft manifest template and validator. It is not a scheduler.
- `tools/intake_store.py`: the local SQLite intake ledger; it atomically persists unique source revisions, current work-item snapshots, a cursor and pending triage events.
- `docs/INTAKE_AND_BEADS.md`: Beads evaluation and limitations of the current intake slice.

Run checks from the repository root (Python 3.11+):

    python3 -m unittest discover -s tests -v
    python3 skills/cron-job/scripts/validate_job.py skills/cron-job/templates/job.example.json

No live collector, scheduled job, Beads installation, event dispatcher or triage agent is wired yet. The existing store is a local prototype, not a production multi-worker queue. Do not interpret a pending outbox row as a delivered event.

## Next slice

Implement read-only GitHub and Jira adapters and durable outbox claiming/acknowledgment, then evaluate a Beads-backed work-item view against the intake ledger contract. Scope and authorization come before enabling any cron schedule.
