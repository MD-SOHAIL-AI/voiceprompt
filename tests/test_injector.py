from __future__ import annotations

import unittest
from unittest.mock import patch

from voiceprompt.injector import TextInjector


class InjectorTests(unittest.TestCase):
    @patch("voiceprompt.injector.time.sleep")
    @patch("voiceprompt.injector.pyperclip")
    def test_does_not_overwrite_clipboard_changed_by_user(self, clipboard, sleep):
        injector = TextInjector()
        injector._generation = 1
        clipboard.paste.return_value = "user copied something else"
        injector._restore_later("previous", "injected", 1)
        clipboard.copy.assert_not_called()

    @patch("voiceprompt.injector.time.sleep")
    @patch("voiceprompt.injector.pyperclip")
    def test_stale_restore_does_not_overwrite_new_dictation(self, clipboard, sleep):
        injector = TextInjector()
        injector._generation = 2
        clipboard.paste.return_value = "injected"
        injector._restore_later("previous", "injected", 1)
        clipboard.copy.assert_not_called()
