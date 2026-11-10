"""Deterministic offline evidence rules and candidate-only remediation."""
import difflib
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
LAB_ROOT = REPO_ROOT / 'examples/baseline'
PATCHABLE_PATHS = (
    'examples/agents/ads/roas.py',
    'examples/agents/ads/skills/campaign_creation/SKILL.md',
    'examples/agents/ads/skills/roas_reporting/SKILL.md',
)
INPUT_PATHS = ('examples/agent_registry.json',) + PATCHABLE_PATHS
WORKER = Path(__file__).resolve().with_name('eval_worker.py')
NOTICE = 'SYNTHETIC OFFLINE FIXTURE — no real model calls or production integration. Subprocess isolation is not a full sandbox.'


def source_digest(root):
    digest = hashlib.sha256()
    for name in sorted(INPUT_PATHS):
        data = (Path(root) / name).read_bytes()
        digest.update(name.encode() + b'\0' + str(len(data)).encode() + b'\0' + data)
    return digest.hexdigest()


def evaluate(root, skill):
    try:
        result = subprocess.run(
            [sys.executable, '-I', '-B', str(WORKER), str(Path(root).resolve()), skill],
            capture_output=True, text=True, timeout=5, env={'PYTHONHASHSEED': '0'},
            cwd=str(WORKER.parent), check=True,
        )
        cases = json.loads(result.stdout)
        return {'passed': bool(cases) and all(c['passed'] is True for c in cases), 'cases': cases}
    except (subprocess.SubprocessError, ValueError, KeyError):
        return {'passed': False, 'cases': [{'name': 'trusted_worker_failure', 'passed': False, 'kind': 'execution'}]}


SCENARIOS = {
    'roas-unit-mismatch': ('roas_reporting', 'unit_mismatch'),
    'campaign-confirmation': ('campaign_creation', 'missing_confirmation'),
    'upstream-timeout': ('roas_reporting', 'upstream_timeout'),
}
IDENTITIES = ('tenant', 'agent', 'skill', 'release', 'skill_version', 'source_hash')


def _token(value):
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ValueError('Invalid evidence identifier')
    return hashlib.sha256(value.encode()).hexdigest()


def _time(value):
    if not isinstance(value, str):
        raise ValueError('Invalid UTC timestamp')
    parsed = datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
    if parsed.strftime('%Y-%m-%dT%H:%M:%SZ') != value:
        raise ValueError('Invalid UTC timestamp')
    return value


def normalize_incident(raw):
    """Allowlist schema. Hash identifiers; discard raw prompts, logs and extras."""
    if raw.get('schema_version') != 1 or raw.get('fixture_mode') is not True:
        raise ValueError('Only explicitly synthetic normalized fixtures are supported')
    def identity(row):
        result = {k: _token(row[k]) for k in ('tenant', 'release', 'skill_version')}
        result['agent'] = row.get('agent') if row.get('agent') in {'Ads-Agent', 'Reporting-Agent', 'Orchestrator'} else 'unsupported'
        result['skill'] = row.get('skill') if row.get('skill') in {'roas_reporting', 'campaign_creation', 'dashboard_summary', 'route_request'} else 'unsupported'
        digest = row.get('source_hash', '')
        result['source_hash'] = digest if isinstance(digest, str) and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest) else 'invalid'
        return result
    incident = identity(raw)
    incident.update(schema_version=1, fixture_mode=True, incident_id=_token(raw['incident_id']),
                    scenario=raw.get('scenario') if raw.get('scenario') in SCENARIOS else 'unsupported',
                    window={k: _time(raw['window'][k]) for k in ('start', 'end')})
    if incident['window']['start'] >= incident['window']['end']:
        raise ValueError('Invalid evidence window')
    incident['events'] = []
    events = raw.get('events', [])
    if not isinstance(events, list) or len(events) > 100:
        raise ValueError('Invalid event collection')
    for row in events:
        event = identity(row)
        event.update({k: _token(row[k]) for k in ('id', 'trace_id', 'correlation_id')})
        event['timestamp'] = _time(row['timestamp'])
        event['kind'] = row.get('kind') if row.get('kind') in {'trace', 'turn', 'error', 'log'} else 'unsupported'
        event['signal'] = row.get('signal') if row.get('signal') in {'unit_mismatch', 'missing_confirmation', 'upstream_timeout'} else 'unsupported'
        incident['events'].append(event)
    incident['quality'] = {}
    for cohort in ('before', 'after'):
        row = raw.get('quality', {}).get(cohort)
        if row is None:
            continue
        quality = identity(row)
        quality.update(id=_token(row['id']), start=_time(row['start']), end=_time(row['end']))
        for key in ('successes', 'total'):
            value = row[key]
            if type(value) is not int or not 0 <= value <= 1_000_000:
                raise ValueError('Invalid quality count')
            quality[key] = value
        incident['quality'][cohort] = quality
    return incident


def evidence_gate(incident, base_hash):
    """Exact joins, not proximity or a quality decline alone."""
    expected = SCENARIOS.get(incident['scenario'])
    valid = expected is not None and incident['agent'] == 'Ads-Agent' and incident['skill'] == expected[0] and incident['source_hash'] == base_hash
    rows = incident['events']
    valid = valid and len(rows) == 4 and {r['kind'] for r in rows} == {'trace', 'turn', 'error', 'log'}
    if valid:
        valid = len({r['id'] for r in rows}) == 4 and len({r['trace_id'] for r in rows}) == 1 and len({r['correlation_id'] for r in rows}) == 1
        valid = valid and all(all(r[k] == incident[k] for k in IDENTITIES) and incident['window']['start'] <= r['timestamp'] < incident['window']['end'] and r['signal'] == expected[1] for r in rows)
    quality = incident['quality']
    decline = False
    if set(quality) == {'before', 'after'}:
        before, after = quality['before'], quality['after']
        valid_quality = all(all(row[k] == incident[k] for k in ('tenant', 'agent', 'skill')) and 0 <= row['successes'] <= row['total'] and row['total'] > 0 and row['start'] < row['end'] for row in (before, after))
        valid_quality = valid_quality and all(after[k] == incident[k] for k in IDENTITIES) and before['id'] != after['id']
        valid_quality = valid_quality and before['end'] <= incident['window']['start'] and after['start'] == incident['window']['start'] and after['end'] == incident['window']['end']
        decline = valid_quality and before['successes'] * after['total'] > after['successes'] * before['total']
    return bool(valid and decline), bool(decline)


def run_incident(repo, incident_path, out_dir):
    repo, out_dir = Path(repo).resolve(), Path(out_dir).resolve()
    incident = normalize_incident(json.loads(Path(incident_path).read_text()))
    out_dir.mkdir(parents=True, exist_ok=False)
    base_hash = source_digest(repo)
    skill = incident['skill']
    joined, decline = evidence_gate(incident, base_hash)
    can_fix = joined and incident['scenario'] != 'upstream-timeout'
    candidate = out_dir / 'candidate'
    for name in INPUT_PATHS:
        target = candidate / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / name, target)
    baseline = evaluate(repo, skill)
    changed = []
    path = PATCHABLE_PATHS[0]
    original = (repo / path).read_text()
    fixed = original.replace('    spend_currency = spend\n', '    spend_currency = spend / 1_000_000 if spend_unit == "micros" else spend\n')
    if can_fix and skill == 'roas_reporting' and original != fixed:
        (candidate / path).write_text(fixed)
        changed.append(path)
    if can_fix and skill == 'campaign_creation':
        path = PATCHABLE_PATHS[1]
        fixed = ('# Campaign creation\n'
                 'Require explicit user confirmation before any campaign creation or mutation.\n'
                 'Show a preview containing budget, audience, creative, and schedule before asking for confirmation.\n'
                 'Silence, ambiguous replies, and prior unrelated consent are not confirmation.\n'
                 'If any preview detail changes, obtain fresh confirmation.\n'
                 'Cancellation or refusal must produce no mutation.\n')
        (candidate / path).write_text(fixed)
        changed.append(path)
    after = evaluate(candidate, skill)
    ready = bool(changed) and not baseline['passed'] and after['passed']
    report = {
        'schema_version': 1, 'fixture_mode': True, 'notice': NOTICE,
        'incident_id': incident['incident_id'], 'scenario': incident['scenario'],
        'fingerprint': hashlib.sha256(json.dumps([incident.get(k) for k in ('incident_id', 'tenant', 'agent', 'skill', 'release', 'window')], sort_keys=True).encode()).hexdigest(),
        'status': 'ready_for_review' if ready else 'needs_human',
        'base_content_hash': base_hash, 'candidate_content_hash': source_digest(candidate),
        'evidence_summary': {'mode': 'synthetic', 'quality_drop_is_not_causal_proof': True, 'exact_join_passed': joined, 'quality_decline': decline},
        'incident_snapshot': incident,
        'diagnosis': {'classification': 'code_defect', 'causal_status': 'reproduced_with_fixture', 'explanation': 'Currency micros mismatch reproduced by trusted holdout evaluation.', 'source_paths': changed},
        'evaluation': {'baseline_passed': baseline['passed'], 'candidate_passed': after['passed'], 'cases': {'baseline': baseline['cases'], 'candidate': after['cases']}},
        'changed_paths': changed,
    }
    if skill == 'campaign_creation':
        report['diagnosis'].update(classification='skill_contract_defect', explanation='Static skill contract regression reproduced; not LLM behavioral proof.')
    if not can_fix:
        report['diagnosis'].update(classification='upstream_failure' if joined else 'insufficient_evidence', causal_status='not_established', explanation='No safe deterministic local fix; human investigation required.', source_paths=[])
    patch = ''.join(''.join(difflib.unified_diff((repo / p).read_text().splitlines(True), (candidate / p).read_text().splitlines(True), fromfile='a/' + p, tofile='b/' + p)) for p in changed)
    (out_dir / 'candidate.patch').write_text(patch)
    (out_dir / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    text = '# Offline candidate review\n\n' + NOTICE + '\n\nStatus: ' + report['status'] + '\n\n' + report['diagnosis']['explanation'] + '\n'
    (out_dir / 'report.md').write_text(text)
    (out_dir / 'pr-body.md').write_text(text)
    return report


def verify_bundle(repo, out_dir):
    """Rebuild the known synthetic scenario, then compare before trusting artifacts.

    This reference gate deliberately accepts only bundled scenarios. It does not
    execute supplied candidate code: it executes a freshly reconstructed candidate
    from the trusted checkout and compares exact bytes, not self-reported hashes.
    """
    import tempfile
    repo, out_dir = Path(repo).resolve(), Path(out_dir).resolve()
    try:
        report_path = out_dir / 'report.json'
        if report_path.is_symlink() or report_path.stat().st_size > 100_000:
            raise ValueError('Invalid report')
        report = json.loads(report_path.read_text(encoding='utf-8'))
        scenario = report.get('scenario')
        if scenario not in SCENARIOS or report.get('status') != 'ready_for_review':
            raise ValueError('No reviewable synthetic candidate')
        candidate = out_dir / 'candidate'
        if candidate.is_symlink() or not candidate.is_dir():
            raise ValueError('Invalid candidate tree')
        actual_files = set()
        for path in candidate.rglob('*'):
            if path.is_symlink():
                raise ValueError('Symlinks are not allowed')
            if path.is_file():
                actual_files.add(path.relative_to(candidate).as_posix())
            elif not path.is_dir():
                raise ValueError('Non-regular candidate entry')
        if actual_files != set(INPUT_PATHS):
            raise ValueError('Unexpected candidate file inventory')
        for name in INPUT_PATHS:
            if (candidate / name).stat().st_size > 100_000:
                raise ValueError('Oversized candidate file')
            source = repo / name
            if any(p.is_symlink() for p in [source, *source.parents]):
                raise ValueError('Untrusted source symlink')
        if source_digest(repo) != report.get('base_content_hash'):
            raise ValueError('Stale baseline')
        # The reference incident is trusted project configuration, not the report.
        fixture = REPO_ROOT / 'examples/incidents' / (scenario + '.json')
        with tempfile.TemporaryDirectory(prefix='.verify-', dir=out_dir) as temp:
            expected_dir = Path(temp) / 'result'
            expected = run_incident(repo, fixture, expected_dir)
            if expected != report or expected['status'] != 'ready_for_review':
                raise ValueError('Report differs from independent reproduction')
            for name in INPUT_PATHS:
                if (candidate / name).read_bytes() != (expected_dir / 'candidate' / name).read_bytes():
                    raise ValueError('Candidate differs from verified repair')
            for name in ('candidate.patch', 'report.md', 'pr-body.md'):
                artifact = out_dir / name
                if artifact.is_symlink() or artifact.stat().st_size > 100_000:
                    raise ValueError('Invalid review artifact')
                if artifact.read_bytes() != (expected_dir / name).read_bytes():
                    raise ValueError('Review artifact was modified')
        return report
    except (OSError, TypeError, KeyError, AttributeError, json.JSONDecodeError):
        raise ValueError('Malformed or missing verification bundle') from None
