import threading
import time
import unittest
from unittest.mock import patch

from voiceprompt.injector import TextInjector, PasteError


class DeliveryReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.clipboard = {'text': 'original', 'sequence': 1}
        def copy(text):
            self.clipboard['text'] = text
            self.clipboard['sequence'] += 1
        patches = [patch('voiceprompt.injector.snapshot_clipboard', return_value=None),
                   patch('voiceprompt.injector.sequence_number', side_effect=lambda: self.clipboard['sequence']),
                   patch('voiceprompt.injector.pyperclip.paste', side_effect=lambda: self.clipboard['text']),
                   patch('voiceprompt.injector.pyperclip.copy', side_effect=copy),
                   patch('voiceprompt.injector.modifiers_down', return_value=False)]
        for item in patches: item.start(); self.addCleanup(item.stop)
        self.injector = TextInjector()

    def test_delayed_consumer_keeps_complete_transcript_after_old_restore_deadline(self):
        consumed = []
        def paste():
            timer = threading.Timer(.35, lambda: consumed.append(self.clipboard['text']))
            timer.start()
            self.addCleanup(timer.join)
        with patch('voiceprompt.injector.paste_shortcut', side_effect=paste):
            self.injector.inject('complete sentence')
            time.sleep(.4)
        self.assertEqual(consumed, ['complete sentence'])

    def test_clipboard_change_between_write_and_shortcut_never_pastes_unrelated_text(self):
        def user_copy(_): self.clipboard.update(text='new user content', sequence=99)
        with patch('voiceprompt.injector.time.sleep', side_effect=user_copy), patch('voiceprompt.injector.paste_shortcut') as paste:
            with self.assertRaises(PasteError) as failure: self.injector.inject('dictation')
        self.assertEqual(failure.exception.reason, 'clipboard_changed')
        paste.assert_not_called()
        self.assertEqual(self.clipboard['text'], 'new user content')

    def test_two_dictations_restore_original_clipboard_not_first_dictation(self):
        with patch('voiceprompt.injector.paste_shortcut'):
            self.injector.inject('first')
            self.injector.inject('second')
        self.assertTrue(self.injector.restore_previous())
        self.assertEqual(self.clipboard['text'], 'original')

    def test_manual_restore_preserves_later_user_copy_even_if_identical(self):
        with patch('voiceprompt.injector.paste_shortcut'): self.injector.inject('sentence')
        self.clipboard['sequence'] += 1
        self.assertFalse(self.injector.restore_previous())
        self.assertEqual(self.clipboard['text'], 'sentence')

    def test_forced_replace_is_explicit_and_skips_unsupported_snapshot(self):
        with patch('voiceprompt.injector.snapshot_clipboard', side_effect=RuntimeError('unsupported')) as snapshot, patch('voiceprompt.injector.paste_shortcut'):
            with self.assertRaises(PasteError): self.injector.inject('sentence')
            self.injector.inject('sentence', replace_clipboard=True)
        self.assertEqual(snapshot.call_count, 1)
