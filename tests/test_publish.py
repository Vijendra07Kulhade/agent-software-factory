"""Publisher policy is tested without GitHub credentials or network."""
import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'factory' / 'publish.py'


class PublisherPlanTests(unittest.TestCase):
    def test_validated_plan_never_contains_a_merge_or_production_command(self):
        self.assertTrue(MODULE.exists(), 'publisher is not implemented yet')
        spec = importlib.util.spec_from_file_location('publisher', MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        plan = module.build_plan({'fingerprint': 'a' * 64,
                                  'status': 'ready_for_review'},
                                 'Vijendra07Kulhade/agent-software-factory')
        self.assertEqual(plan['branch'], 'factory/' + 'a' * 24)
        self.assertTrue(plan['draft'])
        self.assertFalse(plan['auto_merge'])
        self.assertEqual(plan['base'], 'main')


class PublisherBoundaryTests(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location('publisher', MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_rejects_nonreviewable_status_and_argument_injection(self):
        module = self.module()
        with self.assertRaises(ValueError):
            module.build_plan({'status': 'needs_human'}, 'owner/repo')
        for slug in ('--repo', 'a/b/c', 'a/b;touch-file', 'https://github.com/a/b'):
            with self.assertRaises(ValueError):
                module.build_plan({'status': 'ready_for_review', 'fingerprint': 'a'*64}, slug)

    def test_execution_refuses_a_mismatching_remote_before_any_push(self):
        from unittest.mock import patch
        module = self.module()
        self.assertTrue(hasattr(module, '_execute'), 'publication implementation missing')
        report = {'status': 'ready_for_review', 'fingerprint': 'b'*64}
        def fake(args, cwd):
            if args[-3:] == ['remote', 'get-url', 'origin']:
                return 'https://github.com/another/repository.git'
            if 'status' in args:
                return ''
            raise AssertionError('unexpected command: ' + str(args))
        with patch.object(module, '_verified_report', return_value=report):
            with patch.object(module, '_command', side_effect=fake):
                with self.assertRaisesRegex(ValueError, 'origin'):
                    module.publish_bundle(Path('.'), Path('artifacts/example'), 'owner/repo', execute=True)

    def test_remote_readback_must_be_draft_with_exact_head(self):
        module = self.module()
        self.assertTrue(hasattr(module, '_validate_pr'), 'PR readback validation missing')
        plan = module.build_plan({'status': 'ready_for_review', 'fingerprint': 'c'*64}, 'owner/repo')
        data = {'isDraft': True, 'state': 'OPEN', 'headRefName': plan['branch'],
                'baseRefName': 'main', 'headRefOid': 'd'*40,
                'url': 'https://github.com/owner/repo/pull/1'}
        self.assertEqual(module._validate_pr(data, plan, 'd'*40), data['url'])
        for key, bad in [('isDraft', False), ('state', 'MERGED'), ('headRefOid', 'e'*40),
                         ('baseRefName', 'production'), ('url', 'https://evil.invalid/')]:
            with self.assertRaises(ValueError):
                module._validate_pr(dict(data, **{key: bad}), plan, 'd'*40)

    def test_default_path_verifies_but_performs_no_remote_or_git_action(self):
        from unittest.mock import patch
        module = self.module()
        self.assertTrue(hasattr(module, 'publish_bundle'), 'safe publisher path missing')
        report = {'status': 'ready_for_review', 'fingerprint': 'b'*64}
        with patch.object(module, '_verified_report', return_value=report) as verify:
            with patch.object(module, '_command', side_effect=AssertionError('unexpected external action')):
                plan = module.publish_bundle(Path('.'), Path('artifacts/example'), 'owner/repo')
        self.assertEqual(verify.call_count, 1)
        self.assertEqual(plan['mode'], 'dry_run')


class PublisherLocalGitTests(unittest.TestCase):
    def test_execute_uses_real_git_and_readbacks_with_fake_github_transport(self):
        import shutil
        import subprocess
        import tempfile
        from unittest.mock import patch
        from factory.core import INPUT_PATHS, REPO_ROOT, LAB_ROOT, run_incident
        import factory.publish as publisher
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, remote = root / 'repo', root / 'remote.git'
            repo.mkdir()
            def git(*args, cwd=repo):
                return subprocess.run(['git', *args], cwd=cwd, check=True,
                                      capture_output=True, text=True).stdout.strip()
            git('init', '-b', 'main')
            git('config', 'user.name', 'Factory Test')
            git('config', 'user.email', 'factory-test@example.invalid')
            for name in INPUT_PATHS:
                (repo / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(LAB_ROOT / name, repo / name)
            (repo / '.gitignore').write_text('artifacts/\n')
            git('add', '.')
            git('commit', '-m', 'test fixture')
            git('init', '--bare', str(remote))
            git('remote', 'add', 'origin', str(remote))
            git('push', '-u', 'origin', 'main')
            bundle = repo / 'artifacts/run'
            run_incident(repo, REPO_ROOT / 'examples/incidents/roas-unit-mismatch.json', bundle)
            real_command = publisher._command
            calls = []
            def command(args, cwd):
                calls.append(args)
                if args[-3:] == ['remote', 'get-url', 'origin']:
                    return 'https://github.com/owner/repo.git'
                if args[0] != 'gh':
                    return real_command(args, cwd)
                if args[1:3] == ['repo', 'view']:
                    return '{"nameWithOwner":"owner/repo","defaultBranchRef":{"name":"main"}}'
                if args[1:3] == ['pr', 'list']:
                    return '[]'
                if args[1:3] == ['pr', 'create']:
                    self.assertIn('--draft', args)
                    self.assertIn('Synthetic', Path(args[args.index('--body-file') + 1]).read_text())
                    return 'https://github.com/owner/repo/pull/1'
                if args[1:3] == ['pr', 'view']:
                    branch = args[3]
                    return __import__('json').dumps({'url':'https://github.com/owner/repo/pull/1',
                        'isDraft':True, 'state':'OPEN', 'headRefName':branch, 'baseRefName':'main',
                        'headRefOid':git('rev-parse', branch)})
                raise AssertionError(args)
            original = git('rev-parse', 'HEAD')
            with patch.object(publisher, '_command', side_effect=command):
                receipt = publisher.publish_bundle(repo, bundle, 'owner/repo', execute=True)
            self.assertEqual(receipt['mode'], 'published')
            self.assertEqual(git('rev-parse', 'HEAD'), original)
            self.assertEqual(git('status', '--porcelain'), '')
            self.assertTrue((bundle / 'publication.json').exists())
            remote_head = git('--git-dir', str(remote), 'rev-parse', receipt['branch'])
            self.assertEqual(remote_head, receipt['head_commit'])
            self.assertFalse(any('merge' in c or '--force' in c and 'push' in c for c in calls))


if __name__ == '__main__':
    unittest.main()
