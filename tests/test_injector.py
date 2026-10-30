from __future__ import annotations

import unittest
from threading import Thread as RealThread
from unittest.mock import patch, Mock

from voiceprompt.injector import TextInjector


class InjectorTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("voiceprompt.injector.snapshot_clipboard", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("voiceprompt.injector.pyperclip")
    @patch("voiceprompt.injector.snapshot_clipboard", side_effect=RuntimeError("unsupported format"))
    def test_unsupported_clipboard_is_not_overwritten(self, snapshot, clipboard):
        with self.assertRaises(RuntimeError): TextInjector().inject("dictation")
        clipboard.copy.assert_not_called()

    @patch("voiceprompt.injector.pyperclip")
    @patch("voiceprompt.injector.paste_shortcut")
    @patch("voiceprompt.injector.time.sleep")
    def test_cancel_before_shortcut_restores_owned_clipboard(self, sleep, paste, clipboard):
        clipboard.paste.side_effect = ["previous", "text"]
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            TextInjector().inject("text", cancelled=Mock(side_effect=[False,False,True]))
        paste.assert_not_called()
        self.assertEqual(clipboard.copy.call_args_list[-1].args[0], "previous")

    @patch("voiceprompt.injector.pyperclip")
    @patch("voiceprompt.injector.time.sleep")
    @patch("voiceprompt.injector.sequence_number", return_value=5)
    def test_identical_user_copy_is_not_overwritten(self, sequence, sleep, clipboard):
        injector = TextInjector()
        injector._generation = 1
        clipboard.paste.return_value = "injected"
        injector._restore_later("previous", "injected", 1, 4)
        clipboard.copy.assert_not_called()

    @patch("voiceprompt.injector.pyperclip")
    @patch("voiceprompt.injector.paste_shortcut")
    @patch("voiceprompt.injector.foreground_window", side_effect=[10,20])
    @patch("voiceprompt.injector.time.sleep")
    def test_focus_change_during_paste_delay_prevents_shortcut(self, sleep, window, paste, clipboard):
        clipboard.paste.side_effect = ["previous", "text"]
        with self.assertRaisesRegex(RuntimeError, "destination changed"):
            TextInjector().inject("text", target_window=10)
        paste.assert_not_called()
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
    @patch("voiceprompt.injector.paste_shortcut", side_effect=RuntimeError("paste unavailable"))
    @patch("voiceprompt.injector.pyperclip")
    def test_paste_failure_restores_previous_clipboard(self, clipboard, _paste, _sleep):
        clipboard.paste.side_effect = ["previous note", "dictated text"]
        with self.assertRaisesRegex(RuntimeError, "paste unavailable"):
            TextInjector().inject("dictated text")
        self.assertEqual(clipboard.copy.call_args_list[-1].args[0], "previous note")

    @patch("voiceprompt.injector.time.sleep")
    @patch("voiceprompt.injector.paste_shortcut", side_effect=RuntimeError("paste unavailable"))
    @patch("voiceprompt.injector.pyperclip")
    def test_paste_failure_preserves_user_clipboard_change(self, clipboard, _paste, _sleep):
        clipboard.paste.side_effect = ["previous note", "user copied new content"]
        with self.assertRaisesRegex(RuntimeError, "paste unavailable"):
            TextInjector().inject("dictated text")
        self.assertEqual([call.args[0] for call in clipboard.copy.call_args_list], ["dictated text"])

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
