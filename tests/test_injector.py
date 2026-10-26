from __future__ import annotations

import unittest
from threading import Thread as RealThread
from unittest.mock import patch

from voiceprompt.injector import TextInjector


class InjectorTests(unittest.TestCase):
    @patch("voiceprompt.injector.threading.Thread")
    @patch("voiceprompt.injector.time.sleep")
    @patch("voiceprompt.injector.paste_shortcut")
    @patch("voiceprompt.injector.pyperclip")
    def test_clipboard_snapshot_and_paste_are_serialized(self, clipboard, paste, sleep, thread):
        import threading

        injector = TextInjector()
        copied = []
        clipboard.paste.return_value = "original"
        clipboard.copy.side_effect = copied.append
        started = threading.Event()
        finished = threading.Event()

        def competing_injection():
            started.set()
            injector.inject("second")
            finished.set()

        # The competing caller begins while the first paste has the lock.
        competitor = None
        calls = 0
        def paste_action():
            nonlocal competitor, calls
            calls += 1
            if calls == 1:
                competitor = RealThread(target=competing_injection)
                competitor.start()
                self.assertTrue(started.wait(1))
                self.assertFalse(finished.is_set())

        paste.side_effect = paste_action
        injector.inject("first")
        competitor.join(timeout=2)
        self.assertTrue(finished.is_set())
        self.assertEqual(copied, ["first", "second"])

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
