# Operating model: issue to measured recovery

This is the proposed production operating model. The runnable sample implements one synchronous synthetic run, not the durable scheduler, integrations pipeline or deployment controller described here.

## Ownership

| Activity | Accountable owner | Worker/controller responsibility |
|---|---|---|
| Issue scope and severity | Domain on-call / incident commander | Validate input, deduplicate, request missing evidence |
| Access to production telemetry | Platform/security + data owner | Read only approved tenant/project/window; document completeness |
| Causal diagnosis | Owning agent or orchestrator engineer | Rank hypotheses, locate deployed code/skill and propose reproduction |
| Acceptance specification | Domain owner + evaluation owner | Freeze expected outcomes and adversarial cases |
| Repair | Domain engineer | Worker proposes minimal candidate only |
| Independent evaluation | Evaluation/platform owner | Run protected checks on exact baseline and candidate |
| Merge | Repository code owner | Protected CI plus human approval |
| Release/rollback | Release/on-call owner | Staged artifact rollout under separate credentials |
| Incident closure | Domain owner | Confirm quality recovery and no safety regressions |

## Proposed durable state machine

`received -> scoped -> evidence_collected -> investigating -> reproduced -> candidate_created -> independently_verified -> draft_pr -> approved -> canary -> monitoring -> closed`

Alternative transitions:
- Any pre-release state -> `needs_human` for missing permission/provenance, ambiguous cause, budget exhaustion or unsupported repair.
- Evaluation failure -> one bounded repair attempt, then `needs_human`.
- `canary`/`monitoring` -> `rolled_back` on predeclared safety or quality breach.
- Duplicate intake -> link to the active incident, not a second repair.

Production transition records should contain previous/new state, incident fingerprint, actor, timestamp, evidence/config versions, expected revision, and artifact hash. Use transactional compare-and-swap, unique incident keys, expiring worker leases and heartbeats. A crashed worker must not resume a destructive action by replaying it blindly. These mechanisms are not implemented in the local sample.

## Triggering investigations

### User issue
Collect expected versus actual outcome, approved trace reference, tenant scope, environment, UTC window, deployed commit and skill/prompt version. Never request raw conversations in a public GitHub issue. The provided issue form is intake documentation only; it does not trigger production access.

### Looker quality decline
Keep metric/rubric/evaluator version constant, compare equivalent cohorts, disclose denominators and sampling coverage, and inspect uncertainty. The Look must expose governed machine fields or an approved alias map. An aggregate dashboard cannot identify a conversation unless a governed drill-through relation exists. Obtain exact trace IDs rather than guessing them.

Safety-critical events such as unconfirmed campaign mutation can require immediate investigation independent of mean-score significance. First contain harmful writes; the repair factory must not delay incident response.

## Evidence collection

Start with explicit trace IDs and a small, approved time window. Link spans by tenant + trace + parent/tool IDs + deployment. Confirm actual deployed skill/config hashes instead of inspecting the newest main branch. Freeze the collected snapshot and record missing pages/truncated queries. Time proximity alone is not a join.

Normalize and redact before handing evidence to the coding worker. Preserve approved metadata, error codes and quantitative tool results needed for reproduction. Store sensitive raw evidence separately with restricted access. Never copy complete conversation text to PR descriptions.

## Repair gates

1. Human owner agrees on the contract and a discriminating test.
2. Baseline fails the same acceptance check later used for the candidate.
3. Worker cannot edit the authoritative evaluator, CI policy or release controls.
4. Candidate passes relevant domain, neighboring-agent, safety and regression checks.
5. PR clearly says what is observed, inferred, reproduced and verified.
6. Reviewer signs off code/skill changes and residual uncertainty.
7. Release owner approves shadow/canary scope and rollback artifact.

For campaign creation, use a server-enforced consent token bound to tenant, user, exact preview, operation and expiry. Any changed budget/audience/creative/schedule invalidates prior consent. Ambiguous timeouts require operation reconciliation and idempotency, not unconditional retries.

## Audit and retention

Record incident fingerprint, operator scope, collection query IDs/time, evidence redaction version, baseline/candidate commits and skill hashes, model/tool versions, evaluator version, result links, reviewer, publisher and release decisions. Define retention with the data/security owner; do not retain raw telemetry forever. Keep publication audit distinct from model transcripts. Logs must not contain authentication headers or API response bodies.

## Measuring whether the factory helps

Baseline comparable incidents before enabling automation. Track time to scoped evidence, time to reproducible diagnosis, human investigation/review minutes, accepted-patch rate, false root-cause attribution, failed runs/cost, escaped defects and recurrence. Segment by agent/skill and risk, not just average time. Count unsuccessful attempts in the denominator. Do not claim speedups from this synthetic demo.

## Incremental rollout

1. Local fixture lab: no live credentials; inspect every generated patch.
2. Read-only shadow: integrate approved traces/Looks/logs and compare diagnosis with on-call engineers; no publishing.
3. Draft repair pilot: only approved defect classes; protected evaluation and manual merge/release.
4. Release assistance: immutable artifacts, signed provenance, canary measurement and rehearsed rollback under a separate controller.

## Local recovery

Each sample run uses a new output directory. If it fails, keep the old bundle for inspection and choose another path. No retry deletes artifacts. Publication defaults to dry run. If an authorized publish fails after pushing, inspect the remote incident branch and PR before retrying; duplicate detection intentionally stops rather than overwrites. A clean local working tree and matching fetched main are prerequisites.
