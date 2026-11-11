"""Validate the portable cron-job contract (not scheduler installation)."""
import json
import re
import sys
from pathlib import Path

FIELDS = ("version", "id", "status", "owner", "kind", "schedule", "command", "scope", "credentials", "execution", "state", "observability", "permissions")
KEY = ["source", "external_id", "source_revision"]


def validate(job):
    errors = []
    if not isinstance(job, dict):
        return ["job must be an object"]
    errors += [f"missing {key}" for key in FIELDS if key not in job]
    if errors:
        return errors
    if job["version"] != 1 or job["status"] not in ("draft", "approved"):
        errors.append("unsupported version or status")
    for key in ("id", "owner", "kind"):
        if not isinstance(job[key], str) or not job[key].strip():
            errors.append(f"{key} must be nonempty text")
    schedule = job["schedule"]
    if not isinstance(schedule, dict) or schedule.get("timezone") != "UTC" or not isinstance(schedule.get("cron"), str) or not re.fullmatch(r"[^\s]+(?:\s+[^\s]+){4}", schedule["cron"]):
        errors.append("schedule requires a five-field cron string and UTC timezone")
    command = job["command"]
    if not isinstance(command, dict) or not isinstance(command.get("argv"), list) or not command["argv"] or any(not isinstance(x, str) or not x for x in command["argv"]) or not isinstance(command.get("workdir"), str) or not command["workdir"]:
        errors.append("command requires nonempty argv strings and workdir")
    scope = job["scope"]
    if not isinstance(scope, dict) or scope.get("source") not in ("github", "jira") or not isinstance(scope.get("targets"), list) or not scope["targets"] or any(not isinstance(x, str) or not x for x in scope["targets"]):
        errors.append("scope requires github/jira source and nonempty targets")
    credentials = job["credentials"]
    if not isinstance(credentials, dict) or not isinstance(credentials.get("ref"), str) or not credentials["ref"] or "token" in credentials or "password" in credentials:
        errors.append("credentials require a reference, not inline token/password")
    execution = job["execution"]
    if not isinstance(execution, dict) or type(execution.get("timeout_seconds")) is not int or execution["timeout_seconds"] <= 0 or execution.get("concurrency") != "forbid-overlap-per-scope" or not execution.get("retry"):
        errors.append("execution requires positive timeout, overlap policy and retry")
    state = job["state"]
    if not isinstance(state, dict) or not state.get("cursor_store") or state.get("idempotency_key") != KEY:
        errors.append("state requires cursor store and source/external_id/source_revision key")
    obs = job["observability"]
    if not isinstance(obs, dict) or not obs.get("alert_owner") or type(obs.get("max_lag_seconds")) is not int or obs["max_lag_seconds"] <= 0:
        errors.append("observability requires alert owner and positive lag threshold")
    permissions = job["permissions"]
    if not isinstance(permissions, dict) or any(permissions.get(x) is not False for x in ("merge", "deploy", "approve")):
        errors.append("merge/deploy/approve must be false")
    if job["status"] == "approved" and any("TBD" in json.dumps(job.get(x)) for x in ("owner", "scope", "credentials", "state", "observability")):
        errors.append("approved job cannot contain TBD fields")
    return errors


def main():
    if len(sys.argv) != 2:
        print("usage: validate_job.py JOB.json", file=sys.stderr)
        return 2
    try:
        job = json.loads(Path(sys.argv[1]).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"invalid job file: {exc}", file=sys.stderr)
        return 2
    errors = validate(job)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"valid {job['status']} contract: {job['id']} (not installed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
