"""Explicitly authorized draft-PR publication. Never merges or deploys.

GitHub CLI must already be installed and authenticated. The default CLI path is
local verification only. Credentials are never passed as command arguments.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


class PublicationError(ValueError):
    """A publication precondition or remote verification failed."""


def build_plan(report: dict, repository: str) -> dict:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9._-]*', repository):
        raise PublicationError('Expected an explicit GitHub owner/repository')
    if report.get('status') != 'ready_for_review':
        raise PublicationError('Only independently verified candidates can be published')
    fingerprint = report.get('fingerprint', '')
    if not isinstance(fingerprint, str) or not re.fullmatch(r'[0-9a-f]{64}', fingerprint):
        raise PublicationError('Invalid incident fingerprint')
    return {'repository': repository, 'branch': 'factory/' + fingerprint[:24],
            'base': 'main', 'draft': True, 'auto_merge': False,
            'title': 'fix: synthetic Ads-Agent regression ' + fingerprint[:12]}


def _verified_report(repo: Path, bundle: Path) -> dict:
    from factory.core import verify_bundle
    return verify_bundle(repo, bundle)


def _command(args: list[str], cwd: Path) -> str:
    # Suppress raw tool errors: Git errors can include credential-bearing URLs.
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                                check=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        raise PublicationError('External command failed; inspect your local Git/GitHub setup') from None
    return result.stdout.strip()


def publish_bundle(repo: Path, bundle: Path, repository: str, *, execute: bool = False) -> dict:
    report = _verified_report(repo.resolve(), bundle.resolve())
    plan = build_plan(report, repository)
    if not execute:
        return dict(plan, mode='dry_run')
    return _execute(repo.resolve(), bundle.resolve(), report, plan)


def _validate_pr(data: dict, plan: dict, head: str) -> str:
    if not (data.get('isDraft') is True and data.get('state') == 'OPEN'
            and data.get('headRefName') == plan['branch']
            and data.get('baseRefName') == plan['base']
            and data.get('headRefOid') == head):
        raise PublicationError('Remote PR readback does not match the verified candidate')
    url = data.get('url', '')
    if not re.fullmatch(r'https://github\.com/' + re.escape(plan['repository']) + r'/pull/[1-9][0-9]*', url):
        raise PublicationError('Unexpected remote PR URL')
    return url


def _execute(repo: Path, bundle: Path, report: dict, plan: dict) -> dict:
    # This runs ONLY after explicit --execute; never called by the demo or CI.
    import tempfile
    git = ['git', '-c', 'core.hooksPath=/dev/null']
    if _command(git + ['status', '--porcelain'], repo):
        raise PublicationError('Commit or remove working-tree changes before publishing')
    slug = plan['repository']
    remote = _command(git + ['remote', 'get-url', 'origin'], repo)
    if remote not in {f'https://github.com/{slug}.git', f'https://github.com/{slug}',
                      f'git@github.com:{slug}.git'}:
        raise PublicationError('origin does not match the explicitly requested repository')
    info = json.loads(_command(['gh', 'repo', 'view', slug, '--json',
                                'nameWithOwner,defaultBranchRef'], repo))
    if info.get('nameWithOwner') != slug or (info.get('defaultBranchRef') or {}).get('name') != 'main':
        raise PublicationError('This reference publisher requires main as the target default branch')
    _command(git + ['fetch', '--no-tags', 'origin', 'main'], repo)
    head = _command(git + ['rev-parse', 'HEAD'], repo)
    upstream = _command(git + ['rev-parse', 'refs/remotes/origin/main'], repo)
    if head != upstream:
        raise PublicationError('Local HEAD must equal the fetched origin/main; regenerate after updating')
    fields = 'url,isDraft,state,headRefName,baseRefName,headRefOid'
    existing = json.loads(_command(['gh', 'pr', 'list', '--repo', slug, '--head', plan['branch'],
                                    '--state', 'all', '--json', fields], repo))
    if existing:
        # Never silently return an older PR as verification of a different patch.
        raise PublicationError('An incident PR already exists; inspect it rather than create a duplicate')
    if _command(git + ['ls-remote', '--heads', 'origin', 'refs/heads/' + plan['branch']], repo):
        raise PublicationError('Incident branch already exists; inspect the interrupted publication')
    _verified_report(repo, bundle)  # Reject changed input since initial verification.
    from factory.core import PATCHABLE_PATHS, source_digest
    changed = report['changed_paths']
    if not changed or any(p not in PATCHABLE_PATHS for p in changed):
        raise PublicationError('Candidate contains forbidden paths')
    work_parent = bundle / '.worktrees'
    work_parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='publish-', dir=work_parent) as temporary:
        worktree = Path(temporary) / 'checkout'
        added = False
        try:
            _command(git + ['worktree', 'add', '-b', plan['branch'], str(worktree), head], repo)
            added = True
            for relative in changed:
                source = bundle / 'candidate' / relative
                target = worktree / relative
                if source.is_symlink() or target.is_symlink():
                    raise PublicationError('Symlink candidates are forbidden')
                target.write_bytes(source.read_bytes())
            if source_digest(worktree) != report['candidate_content_hash']:
                raise PublicationError('Candidate content changed during publication')
            _command(git + ['add', '--', *changed], worktree)
            _command(git + ['commit', '-m', plan['title']], worktree)
            commit = _command(git + ['rev-parse', 'HEAD'], worktree)
            # Explicit non-force refspec: the worker cannot overwrite main.
            _command(git + ['push', 'origin', 'HEAD:refs/heads/' + plan['branch']], worktree)
            # Do not trust an editable pr-body.md; generate from validated fields.
            body = worktree / '.factory-pr-body.txt'
            body.write_text('## Synthetic reference-factory candidate\n\n'
                'Fixture evidence only; this is not a production diagnosis.\n\n'
                f"Incident fingerprint: `{report['fingerprint']}`\n\n"
                'Baseline reproduction and independent candidate checks passed.\n'
                'Campaign skill checks, if applicable, are static contract checks, not LLM evaluations.\n'
                'Human review and deployment authorization remain required.\n\n'
                'Changed paths:\n' + ''.join(f'- `{p}`\n' for p in changed), encoding='utf-8')
            _command(['gh', 'pr', 'create', '--repo', slug, '--base', 'main',
                      '--head', plan['branch'], '--draft', '--title', plan['title'],
                      '--body-file', str(body)], worktree)
            readback = json.loads(_command(['gh', 'pr', 'view', plan['branch'], '--repo', slug,
                                           '--json', fields], repo))
            url = _validate_pr(readback, plan, commit)
            receipt = dict(plan, mode='published', url=url, head_commit=commit)
            (bundle / 'publication.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
            return receipt
        finally:
            if added:
                _command(git + ['worktree', 'remove', '--force', str(worktree)], repo)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--repository', required=True, help='Explicit owner/repository')
    parser.add_argument('--execute', action='store_true', help='Authorize branch push and draft PR creation')
    args = parser.parse_args()
    try:
        result = publish_bundle(Path(__file__).resolve().parents[1], args.bundle,
                                args.repository, execute=args.execute)
    except (ValueError, OSError, KeyError):
        # Do not expose unexpected remote payloads or telemetry in terminal output.
        parser.exit(2, 'Publication refused; check bundle, clean base, origin, authentication, and existing PRs.\n')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
