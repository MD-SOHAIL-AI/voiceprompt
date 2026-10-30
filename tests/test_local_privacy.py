import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch, MagicMock

from voiceprompt.config import load_settings, Settings, validate_settings, recover_settings
from voiceprompt.credentials import retire_cloud_credentials
from voiceprompt.history import TranscriptionHistory


class LocalPrivacyTests(unittest.TestCase):
    def test_disabled_history_preserves_existing_transcripts(self):
        with tempfile.TemporaryDirectory() as directory:
            history = TranscriptionHistory(Path(directory) / "history.json")
            history.add("existing transcript")
            original = history.path.read_bytes()
            history.limit = 0
            history.add("must not be saved")
            self.assertEqual(history.path.read_bytes(), original)

    def test_corrupt_history_is_not_overwritten_by_next_dictation(self):
        with tempfile.TemporaryDirectory() as directory:
            history = TranscriptionHistory(Path(directory) / "history.json")
            history.path.write_text('{bad', encoding="utf-8")
            with self.assertRaises(ValueError): history.add("new text")
            self.assertEqual(history.path.read_text(), '{bad')
            history.clear()
            self.assertEqual(history.load(), [])
            self.assertEqual(next(history.path.parent.glob('history.unreadable.*.json')).read_text(), '{bad')
    def test_explicit_recovery_preserves_bad_file_and_restores_local_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{bad', encoding="utf-8")
            path.with_suffix('.v6.bak').write_text(json.dumps({"config_version":6,"hotkey":"f9","cleanup_provider":"gemini"}), encoding="utf-8")
            with patch("voiceprompt.config.config_path", return_value=path):
                recover_settings()
                self.assertEqual(load_settings().hotkey, "f9")
            self.assertNotIn("cleanup_provider", json.loads(path.read_text()))
            self.assertEqual(next(path.parent.glob('config.unreadable.*.json')).read_text(), '{bad')
    def test_old_cloud_profile_migrates_without_losing_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = {"config_version": 6, "cleanup_provider": "gemini", "backend": "nemotron", "hotkey": "f9"}
            path.write_text(json.dumps(original), encoding="utf-8")
            with patch("voiceprompt.config.config_path", return_value=path):
                settings = load_settings()
            self.assertEqual(settings.config_version, 7)
            self.assertEqual(settings.backend, "nemotron")
            self.assertEqual(settings.hotkey, "f9")
            self.assertNotIn("cleanup_provider", asdict(settings))
            self.assertEqual(json.loads(path.with_suffix('.v6.bak').read_text()), original)

    def test_removed_provider_settings_cannot_be_enabled(self):
        self.assertFalse(Settings().whisper_phrase_decoding)
        with self.assertRaises(ValueError):
            validate_settings(Settings(), {"cleanup_provider": "openrouter"})

    def test_retirement_only_deletes_application_cloud_keys(self):
        vault = MagicMock()
        with patch.dict("os.environ", {}, clear=True), patch("voiceprompt.credentials.os.name", "nt"), patch("voiceprompt.credentials._backend", return_value=vault):
            self.assertEqual(retire_cloud_credentials(), "")
        self.assertEqual(vault.delete_password.call_count, 2)
        self.assertEqual({call.args for call in vault.delete_password.call_args_list}, {("VoicePrompt.Cleanup", "gemini"), ("VoicePrompt.Cleanup", "openrouter")})

    def test_retirement_failure_and_acceptance_are_safe(self):
        with patch.dict("os.environ", {}, clear=True), patch("voiceprompt.credentials.os.name", "nt"), patch("voiceprompt.credentials._backend", side_effect=RuntimeError("vault unavailable")):
            self.assertTrue(retire_cloud_credentials())
        with patch.dict("os.environ", {"VOICEPROMPT_ACCEPTANCE_DIR": "fixture"}), patch("voiceprompt.credentials._backend") as vault:
            self.assertEqual(retire_cloud_credentials(), "")
            vault.assert_not_called()
