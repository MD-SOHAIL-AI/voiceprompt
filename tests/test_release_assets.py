import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location('release_assets', Path(__file__).resolve().parents[1] / 'scripts/verify_release_assets.py')
assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assets)


class ReleaseAssetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.local, self.hosted = root / 'local', root / 'hosted'
        self.local.mkdir(); self.hosted.mkdir()
        self.installer = 'VoicePrompt-Setup-0.7.1-x64.exe'
        (self.local / self.installer).write_bytes(b'installer')
        (self.local / (self.installer + '.sha256')).write_text(assets.sha256(self.local / self.installer) + '  ' + self.installer)
        (self.local / 'latest.json').write_text('{"signature":"fixture"}')
        self.names = [self.installer, self.installer + '.sha256', 'latest.json']
        for name in self.names: shutil.copy2(self.local / name, self.hosted / name)

    def test_exact_downloaded_bytes_and_sidecar_are_required(self):
        self.assertEqual(len(assets.verify_downloaded(self.local, self.hosted, self.installer, self.names)), 3)

    def test_altered_installer_blocks_promotion(self):
        (self.hosted / self.installer).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'changed'): assets.verify_downloaded(self.local, self.hosted, self.installer, self.names)

    def test_missing_signed_metadata_blocks_promotion(self):
        (self.hosted / 'latest.json').unlink()
        with self.assertRaisesRegex(ValueError, 'missing'): assets.verify_downloaded(self.local, self.hosted, self.installer, self.names)

    def test_matching_but_invalid_sidecar_is_rejected(self):
        for folder in (self.local, self.hosted): (folder / (self.installer + '.sha256')).write_text('bad checksum')
        with self.assertRaisesRegex(ValueError, 'sidecar'): assets.verify_downloaded(self.local, self.hosted, self.installer, self.names)

    def test_stable_verification_cannot_omit_signature_validation(self):
        command = Mock()
        with self.assertRaisesRegex(ValueError, 'signed metadata'):
            assets.verify_draft('v0.7.1', self.local / self.installer, command=command)
        command.assert_not_called()

    def test_published_or_incomplete_draft_is_rejected_before_download(self):
        preview = self.local / 'VoicePrompt-Setup-0.7.1-rc.1-x64-unsigned-preview.exe'
        for draft, names in ((False, []), (True, [])):
            command = Mock(return_value=Mock(returncode=0, stdout=json.dumps({'isDraft': draft, 'tagName': 'v0.7.1-rc.1', 'assets': names})))
            with self.assertRaises(ValueError): assets.verify_draft('v0.7.1-rc.1', preview, command=command)
            self.assertEqual(command.call_count, 1)

    def test_version_or_channel_mismatch_never_downloads(self):
        command = Mock()
        with self.assertRaisesRegex(ValueError, 'filename'):
            assets.verify_draft('v0.7.1-rc.1', self.local / self.installer, command=command)
        command.assert_not_called()

    def test_stable_signature_failure_blocks_success_report(self):
        self.check_stable_draft(signature_valid=False)

    def test_complete_stable_draft_checks_native_signature_after_download(self):
        self.check_stable_draft(signature_valid=True)

    def check_stable_draft(self, *, signature_valid):
        names = self.names + [self.installer + '.signing.json', self.installer + '.update-signing.json']
        for name in names[3:]: (self.local / name).write_text('{}')
        def command(args, **kwargs):
            if args[2] == 'view':
                return SimpleNamespace(returncode=0, stdout=json.dumps({'isDraft': True, 'tagName': 'v0.7.1', 'assets': [{'name': n} for n in names]}))
            destination = Path(args[args.index('--dir') + 1])
            for name in names: shutil.copy2(self.local / name, destination / name)
            return SimpleNamespace(returncode=0)
        verify = Mock(side_effect=None if signature_valid else ValueError('signature invalid'))
        with patch.dict(sys.modules, {'release_updates': SimpleNamespace(verify=verify)}):
            kwargs = dict(metadata=self.local / 'latest.json', native='native.exe', command=command)
            if signature_valid:
                result = assets.verify_draft('v0.7.1', self.local / self.installer, **kwargs)
                self.assertTrue(result['update_signature_verified'])
            else:
                with self.assertRaisesRegex(ValueError, 'signature invalid'):
                    assets.verify_draft('v0.7.1', self.local / self.installer, **kwargs)
                self.assertFalse((self.local / 'v0.7.1.hosted-verification.json').exists())
        verify.assert_called_once()
