# Proposal: ticket-driven agent software factory

## Status and intent

This is the target design described in `Agent.md`. The repository currently implements only an offline intake connector/store slice (see `README.md` and `docs/INTAKE_AND_BEADS.md`), not the complete SDLC. The primary production workflow is ticket-driven: **intake → triage → specification → implementation → verification → review → feedback**. Release is a separately authorized activity after review, not an automatic consequence of a green test or an approved ticket.

## System boundaries and contracts

A ticket in GitHub Issues or Jira is the human-visible source of the request. A durable internal work item is the execution source of truth; it retains the external ticket ID and a link to its source. Comments and status are synchronized explicitly, not treated as executable instructions. Each stage receives the same work-item ID and produces a versioned artifact or decision with provenance. A workflow controller—not a prompt or a cron job—enforces transitions, permissions, retries and human approvals.

Minimum work item: `id`, `source`, `external_id`, `source_url`, `repository`, `title`, `description`, `labels`, `priority`, `assignee`, `source_status`, `source_updated_at`, `revision`, `intake_fingerprint`, `workflow_state`, `artifact_refs`, `owner`, `created_at`, `updated_at`, and `audit_log`. Store sensitive data by reference under restricted access, not in public tickets or PR bodies. Source revisions are immutable snapshots for each decision; later ticket edits cause deliberate re-triage or approval invalidation rather than silently changing the implementation contract.

Flow (with branches):

`discovered → normalized → triaged → [needs_info | waiting | ready_for_spec | ready_for_implementation] → spec_review → implementation → verification → review → [changes_requested | approved] → release_handoff → outcome_observed → closed`

`needs_info` and `waiting` return to triage when new information arrives. Failed verification returns to implementation within a bounded attempt budget; unresolved issues go to a human. A ticket can close as duplicate, invalid, or no-code action with a recorded reason. An incident or quality alert may create/link a ticket through an authorized adapter, but it must not bypass triage and approval. Safety-critical incidents still require an immediate containment path outside this normal delivery queue.

## 1. Intake: multiple scheduled collectors

Run **separate cron jobs** for GitHub Issues and Jira so each has its own credentials, cursor, rate-limit policy and failure isolation. Optional future jobs can poll approved monitoring/quality signals and create or link a ticket; do not imply these exist today. Webhooks can later reduce latency, but scheduled reconciliation remains useful for missed events. The scheduler fires the collector; the collector fetches and normalizes; the workflow service atomically upserts the work item. A cron schedule is not the work queue or the correctness boundary.

| Component | Responsibility | Input → output | Failure behavior |
|---|---|---|---|
| GitHub intake cron | Poll configured repos for new/updated issues, comments and labels | Repo scope + persisted cursor → raw issue snapshots | Retry with backoff; never advance cursor past unpersisted records |
| Jira intake cron | Poll configured projects using authorized API scope | Project/JQL scope + cursor → raw issue snapshots | Same, with independent cursor and rate limits |
| Reconciliation cron | Recheck a bounded lookback window for edits/deletions/missed polls | Source IDs + lookback → corrected snapshots | Deduplicate revisions; alert on drift |
| Stalled-work cron | Detect `needs_info`, stuck claims or pending human reviews | Work-item state → reminders/escalations | Do not advance stages or approve on behalf of humans |
| Optional signal intake cron | Inspect governed quality/observability alerts | Alert ID/cohort/version → proposed linked ticket | Deduplicate and require approved scope; never patch from aggregate score alone |

Each collector calls the same `ticket-intake` skill (a reusable procedure, not the scheduler itself): validate source identity and permissions; paginate completely; fetch relevant comments/linkages; map fields to the canonical schema; redact or reference sensitive content; calculate `(source, external_id, source_revision)` idempotency key; persist snapshot and cursor transactionally; emit a work-item event; record collection gaps and errors. Source-specific adapters implement authentication, pagination, rate-limit handling and mapping. The skill must never merge, edit code, or deploy. A successful poll with zero changes is a normal result; repeated failures page an operator. Poll frequency is configurable per source and bounded by API quotas; no universal interval is prescribed.

If Hermes Agent is used as the scheduler, its cron feature can run separate jobs with a collector skill/workdir; the factory still needs its own durable work-item store and atomic state transitions. Do not equate a scheduled LLM invocation with reliable deduplication, transactional cursors or production tenant isolation. Initially prefer a deterministic collector script invoked on schedule; let an agent handle ambiguous mapping or triage, not basic polling correctness.

## 2. Triage

The triage agent checks duplicate status, repository ownership, request type, risk, completeness and whether an existing spec is sufficient. It assigns exactly one readiness decision: `needs_info`, `waiting`, `ready_for_spec`, or `ready_for_implementation`, with reasons and missing questions. A human owns priority and high-risk classification overrides. Output is `triage.json` containing source revision, decision, owner, rationale, risk, dependencies and next action. A changed ticket or new evidence can reopen triage. No implementation starts from an ambiguous or unauthorized issue.

## 3. Specification

The spec agent converts accepted work into a reviewed contract: `PRODUCT.md` for problem, users, scope, non-goals, user stories and acceptance criteria; `TECH.md` for architecture, interfaces, data/security impact, migration/rollback, dependencies and test strategy. Small, already-clear tickets may record a lightweight spec in the work item rather than generate both files, but still need explicit acceptance criteria and an approver. Product/domain owner and technical owner review the relevant artifacts; approval is bound to a specific ticket revision and artifact hashes. If the contract changes, return to review before implementation resumes.

## 4. Implementation

An implementation worker checks out the intended repository revision in an isolated worktree, reads the approved spec, limits changes to the authorized repo/scope, and produces a small patch with tests and a change summary. It has no production credentials and cannot edit the authoritative evaluator, policy gates or release controls. Preserve the original issue ID in branch/commit/PR metadata. For a bug, first demonstrate the baseline failure when feasible; for new functionality, map tests to acceptance criteria. Unexpected dependencies or scope expansion return to triage/specification for approval.

## 5. Verification

A separate verification role runs trusted unit, integration and regression checks against the exact candidate commit, plus UI/browser or domain-specific behavior checks where applicable. It records commands, environment, test identities, results, evidence links, unmet acceptance criteria and known gaps in `verification.json`. Worker-authored tests are useful but not sufficient as an independent gate. A failing or inconclusive check returns a bounded repair task; never mark a static instruction check as proof of runtime safety. For agent behavior, include controlled replay and negative/adversarial cases when available.

## 6. Review and handoff

The review agent compares the issue, approved spec, diff and verification evidence; checks correctness, security, maintainability and unintended changes; and writes `review.json` with findings and a recommendation. The repository owner makes the merge decision; security/domain owners join for high-risk changes. A draft PR links the ticket and artifacts, and protected CI evaluates the actual merge candidate. New commits invalidate commit-specific verification and approval. Approval may hand off an immutable artifact to a separately authorized release owner; production deployment, canary measurement, rollback and final closure are explicit operational gates, not automated review side effects.

## 7. Feedback loop

An observer agent or periodic metrics job records cycle time by stage, queue age, rework, failed verification, reviewer corrections, escaped defects, recurrence, cost and post-release outcomes. It proposes improvements to triage rules, templates, skills and tests with evidence and a human owner. It cannot silently rewrite policy, evaluator, approvals or its own permissions. Feed confirmed defects back into regression suites; keep unsuccessful and no-patch cases in the denominator. Close the ticket only after the agreed acceptance/release observation condition, or record why it ended without deployment.

## Cross-cutting design

- **Orchestrator/state store:** durable work items, compare-and-swap transitions, unique source keys, worker leases, bounded retries, audit trail and dead-letter/escalation queue. Workers can restart without replaying a destructive action.
- **Agent/skill/tool layers:** agents decide and coordinate stages; skills encode reusable procedures (intake normalization, triage, spec writing, testing, review); tools execute source API reads, Git operations, builds and evidence retrieval. The scheduler triggers jobs but is not a skill.
- **Security and provenance:** least-privilege credentials per collector and publisher, tenant/repo authorization, prompt-injection-resistant treatment of ticket text, redaction, immutable evidence refs, commit and artifact hashes, and human gates for mutation. A threat model for the new ticket-driven workflow is still required before live integrations.
- **Observability:** per-job cursor, last success, lag, API errors, dedupe count, work-item transitions, stage durations and artifact links; alerts on missed polls or stuck work. Read deployed telemetry only under approved scope; do not infer causality from a dashboard decline alone.
- **Contracts:** machine-readable versioned schemas for `work-item`, `triage.json`, `spec-approval`, `verification.json`, `review.json` and transition events. Validate at every handoff and keep all artifacts linked to source revision and candidate commit.

## Incremental implementation proposal

1. **Foundation:** define schemas/state machine and a local fixture for GitHub and Jira issues; implement idempotent normalization/upsert and tests for edits, duplicates, pagination and cursor recovery.
2. **Scheduled intake:** configure separate GitHub/Jira cron jobs plus reconciliation and failure alerts, initially read-only against narrowly scoped test projects. Validate persistence and restart behavior; do not use cron output alone as state.
3. **Triage/specification:** add readiness decisions, human review, revision-bound approvals and artifact contracts; test missing-info and changed-ticket paths.
4. **Implementation/verification/review:** implement these stages for approved tickets with independent checks, draft PRs and human merge. Do not treat intake fixtures as proof of downstream behavior.
5. **Feedback and controlled release handoff:** measure outcomes and add separately approved rollout/rollback integration only after the earlier gates work.

Acceptance for the first usable slice: two independently scheduled collectors ingest the same externally edited issue exactly once per source revision; retries and restarts preserve cursor and work-item state; triage produces a reasoned readiness decision; an approved spec leads to a candidate whose verification and review artifacts link back to the ticket; no stage can bypass approval, and no cron job can merge or deploy. This is a proposal and these criteria are not yet implemented or verified.
