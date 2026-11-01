import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from voiceprompt.config import load_settings, Settings
from voiceprompt.release import releases_url
from voiceprompt.windows import paste_shortcut


class ReleaseSafetyTests(unittest.TestCase):
    def test_migration_backs_up_without_changing_vocabulary_or_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = {"config_version": 5, "backend": "nemotron", "nemotron_device": "cpu",
                        "replacements": {"brahm sosh": "Brahmshosh", "my app": "MyApp"}}
            path.write_text(json.dumps(original), encoding="utf-8")
            with patch("voiceprompt.config.config_path", return_value=path):
                result = load_settings()
            self.assertEqual(json.loads(path.with_suffix(".v5.bak").read_text()), original)
            self.assertEqual(result.replacements["brahm sosh"], "Brahmshosh")
            self.assertEqual(result.backend, "nemotron")
            self.assertEqual(result.nemotron_device, "cpu")
            self.assertTrue(result.onboarding_completed)

    def test_bad_settings_are_never_overwritten_with_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("{broken", encoding="utf-8")
            with patch("voiceprompt.config.config_path", return_value=path):
                with self.assertRaises(ValueError):
                    load_settings()
            self.assertEqual(path.read_text(), "{broken")

    def test_new_profiles_have_neutral_defaults_and_no_cloud_cleanup(self):
        settings = Settings()
        self.assertFalse(settings.onboarding_completed)
        self.assertNotIn("Brahmshosh", settings.replacements.values())
        self.assertFalse(hasattr(settings, "cleanup_provider"))
        self.assertEqual(settings.backend, "whisper")
        self.assertFalse(settings.noise_suppression)

    def test_update_link_is_the_confirmed_public_repository(self):
        self.assertEqual(releases_url(), "https://github.com/MD-SOHAIL-AI/voiceprompt/releases")

    @patch("voiceprompt.windows.ctypes.WinDLL")
    def test_paste_uses_pointer_sized_windows_inputs_and_releases_control(self, library):
        library.return_value.SendInput.return_value = 4
        paste_shortcut()
        count, inputs, size = library.return_value.SendInput.call_args.args
        self.assertEqual(count, 4)
        self.assertEqual(size, 40)
        self.assertEqual([(item.keyboard.vk, item.keyboard.flags) for item in inputs],
                         [(0xA2, 0), (0x56, 0), (0x56, 2), (0xA2, 2)])
