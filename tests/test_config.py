from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from voiceprompt.config import load_settings


class ConfigMigrationTests(unittest.TestCase):
    def test_sound_preference_defaults_on_and_preserves_false(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            with patch("voiceprompt.config.config_path", return_value=path):
                path.write_text('{}')
                self.assertTrue(load_settings().sound_feedback)
                path.write_text('{"sound_feedback": false}')
                self.assertFalse(load_settings().sound_feedback)

    def test_migrates_model_and_removes_unsafe_replacements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "model": "base.en",
                        "replacements": {
                            "cloud": "claude",
                            "God": "claude",
                            "my project": "MyProject",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch("voiceprompt.config.config_path", return_value=path):
                settings = load_settings()

        self.assertEqual(settings.model, "base.en")
        self.assertNotIn("cloud", settings.replacements)
        self.assertNotIn("God", settings.replacements)
        self.assertEqual(settings.replacements["my project"], "MyProject")
        self.assertNotIn("brahmsulge", settings.replacements)
        self.assertEqual(settings.config_version, 6)
        self.assertEqual(settings.backend, "whisper")
        self.assertEqual(settings.cpu_threads, 4)
        self.assertFalse(settings.noise_suppression)

    def test_new_options_are_validated_without_switching_legacy_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"model": "tiny.en", "backend": "unknown", "cpu_threads": 99, "capture_mode": "invalid"}))
            with patch("voiceprompt.config.config_path", return_value=path):
                settings = load_settings()
        self.assertEqual(settings.backend, "whisper")
        self.assertEqual(settings.model, "tiny.en")
        self.assertEqual(settings.cpu_threads, 12)
        self.assertEqual(settings.capture_mode, "auto")

    def test_parakeet_settings_migrate_and_retain_whisper_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"config_version": 3, "backend": "parakeet", "model": "base.en", "beam_size": 3, "language": ""}))
            with patch("voiceprompt.config.config_path", return_value=path):
                settings = load_settings()
        self.assertEqual(settings.config_version, 6)
        self.assertEqual(settings.backend, "parakeet")
        self.assertEqual(settings.model, "base.en")
        self.assertEqual(settings.beam_size, 3)
        self.assertEqual(settings.language, "en")

    def test_nemotron_settings_keep_existing_dictation_preferences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"config_version": 4, "backend": "nemotron", "nemotron_device": "cpu", "hotkey": "f8", "model": "small.en", "language": "auto", "replacements": {"my project": "MyProject"}}))
            with patch("voiceprompt.config.config_path", return_value=path):
                settings = load_settings()
            self.assertEqual(settings.backend, "nemotron")
            self.assertEqual(settings.nemotron_device, "cpu")
            self.assertEqual(settings.language, "en")
            self.assertEqual(settings.hotkey, "f8")
            self.assertEqual(settings.model, "small.en")
            self.assertEqual(settings.replacements["my project"], "MyProject")
            path.write_text(json.dumps({"backend": "nemotron", "nemotron_device": "cuda"}))
            with patch("voiceprompt.config.config_path", return_value=path):
                self.assertEqual(load_settings().nemotron_device, "vulkan")


if __name__ == "__main__":
    unittest.main()
