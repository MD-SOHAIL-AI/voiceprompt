import unittest
from unittest.mock import patch

from voiceprompt.startup import APP_NAME, LEGACY_APP_NAMES, set_startup, startup_enabled


class StartupTests(unittest.TestCase):
    def test_disable_cleans_all_historical_startup_names_even_without_current_entry(self):
        with patch("voiceprompt.startup.winreg") as registry:
            registry.DeleteValue.side_effect = [FileNotFoundError(), None, None]
            set_startup(False)
        self.assertEqual([call.args[1] for call in registry.DeleteValue.call_args_list],
                         [APP_NAME, *LEGACY_APP_NAMES])

    def test_enable_migrates_old_names_to_current_command(self):
        with patch("voiceprompt.startup.winreg") as registry, \
             patch("voiceprompt.startup.executable_command", return_value='"C:\\Apps\\VoicePrompt.exe"'):
            set_startup(True)
        self.assertEqual(registry.SetValueEx.call_args.args[1], APP_NAME)
        self.assertEqual([call.args[1] for call in registry.DeleteValue.call_args_list], list(LEGACY_APP_NAMES))

    def test_prompt_voice_legacy_entry_is_detected(self):
        with patch("voiceprompt.startup.winreg") as registry:
            registry.QueryValueEx.side_effect = [FileNotFoundError(), FileNotFoundError(), ("old command", 1)]
            self.assertTrue(startup_enabled())

