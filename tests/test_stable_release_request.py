import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import start_stable_release as release

SHA = 'a' * 40


def event():
    return {'repository': {'full_name': release.REPOSITORY}, 'workflow_run': {
        'head_repository': {'full_name': release.REPOSITORY}, 'event': 'push',
        'head_branch': 'main', 'status': 'completed', 'conclusion': 'success',
        'head_sha': SHA, 'head_commit': {'message': 'Ship 0.7.1 [publish-stable]'}}}


class StableReleaseRequestTests(unittest.TestCase):
    def test_untrusted_failed_unmarked_or_non_main_runs_cannot_request_a_tag(self):
        cases = [('event', 'pull_request'), ('head_branch', 'feature'),
                 ('status', 'in_progress'), ('conclusion', 'failure'),
                 ('head_sha', '--option'), ('head_commit', {'message': 'Routine merge'}),
                 ('head_repository', {'full_name': 'other/fork'})]
        for key, value in cases:
            candidate = event()
            candidate['workflow_run'][key] = value
            with self.subTest(key=key), patch.object(release, 'run') as run:
                with self.assertRaises(ValueError):
                    release.start(candidate)
                run.assert_not_called()
        candidate = event()
        candidate['repository']['full_name'] = 'other/repository'
        with self.assertRaises(ValueError):
            release.requested_commit(candidate)

    def exercise(self, *, existing=None, version='0.7.1', head=SHA, failure=None,
                 notes=True):
        self.calls = []
        def command(args, root):
            self.calls.append(args)
            if failure and failure in args:
                raise subprocess.CalledProcessError(1, args)
            if args[:2] == ['git', 'rev-parse']:
                return head
            if 'api' in args:
                if 'POST' in args:
                    return json.dumps({'ref': 'refs/tags/v0.7.1',
                                       'object': {'type': 'commit', 'sha': SHA}})
                return json.dumps(existing or [])
            return ''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'pyproject.toml').write_text(f'version = "{version}"\n')
            (root / 'docs').mkdir()
            if notes:
                (root / f'docs/release-notes-{version}.md').write_text('Release notes')
            with patch.object(release, 'run', side_effect=command):
                release.start(event(), root)

    def test_tags_exact_verified_commit_and_explicitly_dispatches(self):
        self.exercise()
        create = next(args for args in self.calls if 'POST' in args)
        self.assertIn(f'sha={SHA}', create)
        self.assertIn('ref=refs/tags/v0.7.1', create)
        self.assertEqual(self.calls[-1], ['gh', 'workflow', 'run', 'release.yml',
                                        '--repo', release.REPOSITORY, '--ref', 'v0.7.1'])

    def test_existing_same_commit_can_retry_without_moving_the_tag(self):
        self.exercise(existing=[{'ref': 'refs/tags/v0.7.1', 'object': {
            'type': 'commit', 'sha': SHA,
            'url': f'https://api.github.com/repos/{release.REPOSITORY}/git/commits/{SHA}'}}])
        self.assertFalse(any('POST' in args for args in self.calls))
        self.assertIn('workflow', self.calls[-1])

    def test_existing_different_or_annotated_tag_is_never_replaced(self):
        for kind in ('commit', 'tag'):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.exercise(existing=[{'ref': 'refs/tags/v0.7.1',
                    'object': {'type': kind, 'sha': 'b' * 40}}])
            self.assertFalse(any('POST' in args or 'workflow' in args for args in self.calls))

    def test_checkout_prerelease_missing_notes_and_validation_failure_block_tagging(self):
        for options in ({'head': 'b' * 40}, {'version': '0.7.1-rc.1'}, {'notes': False}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.exercise(**options)
            self.assertFalse(any('api' in args for args in self.calls))
        for failure in ('merge-base', 'scripts/verify_versions.py', 'api'):
            with self.subTest(failure=failure), self.assertRaises(subprocess.CalledProcessError):
                self.exercise(failure=failure)
            self.assertFalse(any('workflow' in args for args in self.calls))
