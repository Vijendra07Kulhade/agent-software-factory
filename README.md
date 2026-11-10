# Agent Software Factory

A runnable, dependency-free reference for investigating failures in a multi-domain agent system and producing evidence-backed repair candidates.

**Scope:** synthetic offline lab, plus optional read-only API adapters and an explicitly authorized draft-PR publisher. This is not a production incident responder, a general autonomous RCA engine, or a deployed multi-agent service. The demo uses deterministic rules and predefined repair recipes; it does not call Claude or any other model.

## Start here

Python 3.11+ and Git are sufficient. No packages, model tokens or credentials are needed for the demo. Run from the repository root:

```sh
python -m unittest discover -s tests -v
python -m factory demo --scenario roas-unit-mismatch --out artifacts/roas
python -m factory verify --bundle artifacts/roas
python -m factory demo --scenario campaign-confirmation --out artifacts/campaign
python -m factory verify --bundle artifacts/campaign
python -m factory demo --scenario upstream-timeout --out artifacts/timeout
```

Output directories must be new. For a repeat run use a different directory; the factory never silently overwrites a previous investigation. `make test`, `make demo` and `make verify` are equivalent conveniences using `python3`.

Expected outcomes:

| Scenario | Root-cause example | Result |
|---|---|---|
| `roas-unit-mismatch` | Spend micros treated as whole currency in Ads-Agent code | Baseline replay fails, repaired candidate passes, `ready_for_review` |
| `campaign-confirmation` | Campaign skill lacks explicit confirmation/preview/cancellation contract | Static contract fails then passes, `ready_for_review`; NOT proof of LLM behavior |
| `upstream-timeout` | Correlated upstream tool timeout, no established local repair | `needs_human`, empty patch |

Inspect `artifacts/roas/report.json`, `report.md`, `candidate.patch`, `pr-body.md`, and `candidate/`. No sample source is modified in place. The fixture's numerical quality scores are synthetic inputs, not measurements of model quality.

## What the sample demonstrates

1. Accept a normalized synthetic incident with agent/skill/release and a UTC window.
2. Join trace, turn, error and log records using exact tenant, trace/correlation, release, skill-version and source-hash identities.
3. Use a synthetic before/after quality cohort as context, not causal proof by itself.
4. Identify one of the known Ads-Agent code/skill defects or decline to patch.
5. Copy only registered sample inputs into a candidate tree.
6. Reproduce the defect and run a trusted evaluator outside that tree.
7. Produce a review bundle with base/candidate hashes, tests and a minimal patch.
8. Independently regenerate the known scenario and compare exact report/artifact/candidate bytes before verification or publication.
9. Optionally create a draft PR using a separate, explicit publishing command. Never merge or deploy.

`examples/agent_registry.json` describes Ads-Agent, Reporting-Agent and Orchestrator skill mappings. Automated repairs are implemented only for the two Ads-Agent examples; other agent causes require escalation and a new approved reproduction/repair rule. The current rules use an explicit code allowlist; the registry is documentation and a hashed input, not a dynamic plugin loader or authorization service.

## Frozen baseline versus working target

`examples/baseline/` contains the intentionally defective, frozen input snapshot. `demo` and the unit tests use it so the lab remains repeatable after a proposed change to `examples/agents/` is accepted. Do not repair the frozen fixture to make a test green.

`triage` operates against the working repository inputs:

```sh
python -m factory triage --incident examples/incidents/roas-unit-mismatch.json --out artifacts/custom-run
```

This still accepts only `fixture_mode: true`; real production records are deliberately rejected. A changed working baseline requires updated, reviewed provenance rather than silently reusing stale evidence.

`verify` verifies against the frozen lab. The publisher additionally verifies against the current working repository and its fetched `origin/main`, so it refuses a stale/already-fixed baseline. Only exact bundled scenarios can pass the reference publication gate; modified synthetic fixtures may be triaged but are not automatically publishable.

## Documents

- [Project proposal and full SDLC](docs/PROPOSAL.md): architecture, Langfuse/Looker/log correlation, alternative causes, sample investigations, evaluation and rollout.
- [Threat model](docs/THREAT_MODEL.md): permissions, injection, privacy, isolation and trust boundaries.
- [Operating model](docs/OPERATING_MODEL.md): ownership, incident states, human gates, metrics and rollout checklist.
- [Integration guide](docs/INTEGRATIONS.md): adapter APIs, schemas, credentials, limitations and production mapping work.
- [Claude Code workflow](docs/CLAUDE_CODE.md): how to use Claude as a supervised investigator/implementer without confusing instructions with controls.
- [Verification record](docs/VERIFICATION.md): execution results and untested boundaries.

## Optional external integrations

`factory/integrations.py` supplies:

- `LangfuseClient.fetch_trace(trace_id)`: explicit-ID retrieval; raw sensitive data stays in memory until the caller sanitizes it.
- `LookerClient.run_look(look_id)`: login and read a pre-created Look; no arbitrary SQL or dashboard editing.
- `read_log_export(...)`: bounded local JSONL export, filtered by tenant, trace IDs, deployment and half-open UTC/timezone-aware interval.
- `sanitize_record(...)`: allowlisted metadata only; strips messages, input/output and unknown metadata. It is not a general secret detector.

These are optional library adapters, not a live collector wired into the synthetic remediation engine. Tests use fake HTTP transports; no actual Langfuse, Looker, model or production server has been accessed. An operator must supply a governed field mapping, scoped authentication, source completeness checks and real behavioral evaluations before enabling live repairs.

## Local Git delivery and pushing yourself

The delivered directory is a local Git repository on `main`; no GitHub repository or PR was created during delivery. After reviewing the files, authenticate your GitHub CLI and run:

```sh
gh auth status
gh repo create Vijendra07Kulhade/agent-software-factory --private --source . --remote origin --push
```

If that repository already exists, do not recreate or overwrite it; inspect it and configure the intended remote yourself. Enable branch protection requiring CI and owner approval. `CODEOWNERS` alone does not enforce reviews. The included Actions workflow has read-only permissions and no production secrets; its remote execution is unverified until you push.

## Optional draft PR publication

Requires GitHub CLI installed/authenticated, a clean committed checkout, `main` as the remote default branch, and local HEAD equal to fetched `origin/main`.

Local verification only, no network or Git mutation:

```sh
python -m factory.publish --bundle artifacts/roas --repository Vijendra07Kulhade/agent-software-factory
```

Only when you explicitly want to push a repair branch and open a real draft PR:

```sh
python -m factory.publish --bundle artifacts/roas --repository Vijendra07Kulhade/agent-software-factory --execute
```

The publisher refuses a mismatching origin, stale base, edited bundle, duplicate PR or pre-existing incident branch. It copies only allowed changes into a new Git worktree, checks the copied content hash, commits, pushes a non-force branch refspec, creates a draft and reads back its draft status, base and exact head commit. It never merges. Interrupted remote publication may leave a branch; inspect it manually rather than deleting or overwriting automatically. Local branch retention after publication is intentional.

The full publishing flow is tested with real temporary local Git repositories and mocked GitHub CLI responses. No actual GitHub publication was performed. Sample fixes are a learning exercise, not authorization to mutate campaign state.

## Production readiness boundary

Not implemented: authenticated alert webhooks, durable queue/leases, distributed deduplication, tenant authorization service, cloud-log query adapters, unrestricted LLM repair, real conversation replay, signed attestations, canary deployment or automatic rollback.

The trusted evaluator uses subprocesses but is **not a security sandbox**. Do not run it against arbitrary repositories or untrusted code. Production implementation workers need disposable externally isolated environments without production credentials. Safety-critical campaign confirmation must be enforced at the mutation API boundary in code; skill prose is insufficient.

No `CLAUDE.md` or executable `.claude/` configuration was installed: the protected-file approval did not complete. The documentation describes the workflow without changing your agent's instructions.
