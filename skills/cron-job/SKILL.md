---
name: cron-job
description: "Use when defining or changing a scheduled factory job. Produce a portable job contract, test it, then bind it to an approved scheduler."
---

# Write a scheduled factory job

Use this skill to create or revise a scheduled job, especially an intake collector. A **skill is a procedure for writing jobs**; a scheduler (Hermes cron, Kubernetes CronJob, systemd timer, etc.) fires them. This skill does not install a scheduler or authorize live polling.

## Inputs to obtain

- Job ID, owner, purpose and source/project/repository scope.
- UTC five-field cron expression and explicit timezone (initially `UTC` only); or record that a scheduler-specific feature is required. Never infer a local timezone.
- Entrypoint executable/arguments, workdir, timeout, concurrency policy, retry/backoff, alert destination, credential reference and permissions.
- Cursor store and idempotency key; expected output and health/lag thresholds.

If a required field is unknown, mark the manifest `draft` and ask the owner. Do not invent credentials, endpoints or a production schedule.

## Procedure

1. Create a JSON job manifest using `templates/job.example.json` as a starting point. The portable contract has `version`, `id`, `status`, `owner`, `kind`, `schedule`, `command`, `scope`, `credentials`, `execution`, `state`, `observability`, and `permissions`. Keep secrets outside the file: `credentials.ref` is a secret-manager reference, never a token. Do not interpolate untrusted ticket text into shell commands.
2. Use separate jobs per intake source (e.g. GitHub and Jira), separate cursors and least-privilege credentials. Use a deterministic collector script for pagination and persistence; agent reasoning can follow after successful intake.
3. Define failure semantics before enabling: persist each source revision with a unique `(source, external_id, source_revision)` key; advance a cursor only after all fetched pages/snapshots it covers are durably stored. If the store cannot commit cursor and records atomically, replay a bounded overlap on restart and deduplicate by that key. A partial run must be safe to repeat.
4. Choose a no-overlap policy per scope and a lease/lock at the work-item store (scheduler overlap prevention is not sufficient). On timeout, rate limit, auth failure, malformed data or incomplete pagination, fail visibly, keep the previous safe cursor and notify the owner. Do not print ticket bodies, credentials or raw traces in logs.
5. Validate the portable manifest with `python3 skills/cron-job/scripts/validate_job.py path/to/job.json` from the repository root. Run a dry-run collector against fixture pages including duplicates, an edit, pagination, and an interrupted final page. Confirm persisted state/cursor after restart and that zero-new-item runs succeed. If no collector exists yet, stop at a `draft` job; do not claim end-to-end verification.
6. Map the validated contract to a scheduler-specific adapter. Confirm schedule parsing, timezone, execution identity, overlap, timeout, retry, output delivery and enabled/paused state in the target scheduler. The adapter must not silently change semantics. Verify one manual run and inspect its durable records before enabling recurring execution. Record adapter configuration/ID and rollback (pause job) in the change review.

## Scheduler-neutral guarantees

- Schedule means **at-least-once attempt**, not exactly-once delivery. The durable intake store owns idempotency.
- No job may merge, deploy, mutate campaigns, or approve SDLC gates. Collector credentials are read-only to ticket APIs and restricted write to intake state.
- `status: draft` means design only; do not install or enable it. `status: approved` means owner approved the contract, not that a scheduler has installed it.
- `schedule.cron` is a standard five-field expression in UTC; nonstandard intervals, seconds, daylight-saving behavior, missed-fire catchup, jitter and retry schedules require an explicit adapter extension and separate review.
- Track last attempt, last successful persisted cursor, source lag, fetched/inserted/deduplicated counts, errors and incomplete pages; alert on missed runs and prolonged lag.

## Output and handoff

Deliver the manifest, a mapping note for the chosen scheduler (or `not selected`), dry-run evidence, owner approval status and remaining gaps. For this repository's first slice, use separate GitHub/Jira draft manifests; no live API access or cron registration is implied. The ticket-intake normalization skill and collector implementation are separate follow-on work.
