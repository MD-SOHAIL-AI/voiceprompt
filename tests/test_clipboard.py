import ctypes
import unittest
from unittest.mock import Mock, patch

from voiceprompt.clipboard import ClipboardUnavailable, ClipboardSnapshot, MAX_SNAPSHOT_BYTES, _snapshot_formats, _ClipboardOwner, DelayedText


class ClipboardSnapshotTests(unittest.TestCase):
    def snapshot(self, contents, *, formats=None, sizes=None):
        buffers = {kind: ctypes.create_string_buffer(data) for kind, data in contents.items()}
        kinds = list(formats if formats is not None else contents)
        user, kernel = Mock(), Mock()
        user.EnumClipboardFormats.side_effect = kinds + [0]
        user.GetClipboardData.side_effect = lambda kind: kind
        kernel.GlobalSize.side_effect = lambda kind: (sizes or {}).get(kind, len(contents[kind]))
        kernel.GlobalLock.side_effect = lambda kind: ctypes.addressof(buffers[kind])
        result = _snapshot_formats(user, kernel)
        return result, user, kernel

    def test_screenshot_preserves_dib_and_png_without_treating_bitmap_as_memory(self):
        dib, png = b'image pixels', b'encoded png'
        result, user, _ = self.snapshot({8: dib, 0xC001: png}, formats=[2, 8, 0xC001])
        self.assertEqual(result, [(8, dib), (0xC001, png)])
        self.assertEqual([call.args[0] for call in user.GetClipboardData.call_args_list], [8, 0xC001])

    def test_synthesized_bitmap_palette_and_dib_are_saved_once_as_dibv5(self):
        result, user, _ = self.snapshot({17: b'rich image'}, formats=[2, 8, 9, 17])
        self.assertEqual(result, [(17, b'rich image')])
        user.GetClipboardData.assert_called_once_with(17)

    def test_large_screenshot_above_old_eight_mb_limit_is_preserved(self):
        pixels = b'x' * (9 * 1024 * 1024)
        result, _, _ = self.snapshot({8: pixels}, formats=[2, 8])
        self.assertEqual(result, [(8, pixels)])

    def test_snapshot_remains_bounded_before_copying_oversized_data(self):
        with self.assertRaisesRegex(ClipboardUnavailable, '64 MB'):
            self.snapshot({8: b'pixels'}, sizes={8: MAX_SNAPSHOT_BYTES + 1})

    def test_rich_text_file_lists_and_registered_formats_remain_intact(self):
        data = {13: b'unicode', 0xC001: b'html', 15: b'file list', 16: b'locale'}
        result, _, _ = self.snapshot(data)
        self.assertEqual(result, list(data.items()))

    def test_unsupported_native_handles_still_fail_without_modifying_clipboard(self):
        with self.assertRaisesRegex(ClipboardUnavailable, 'format 14'):
            self.snapshot({}, formats=[14])


class ClipboardOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.owner = _ClipboardOwner.__new__(_ClipboardOwner)
        self.owner.thread_id = __import__('threading').get_ident()
        self.owner.window = 100
        self.owner.user, self.owner.kernel = Mock(), Mock()
        self.owner.user.GetClipboardOwner.return_value = 100
        self.owner.user.OpenClipboard.return_value = True
        self.owner.user.EnumClipboardFormats.side_effect = [13, 1, 7, 16, 0]
        self.owner.user.GetClipboardData.return_value = 200
        self.lease = DelayedText(self.owner, 'full transcript', 300)
        self.lease.sequence, self.lease.rendered = 10, True
        self.owner.current = self.lease
        self.data = ctypes.create_string_buffer(('full transcript\0').encode('utf-16-le'))
        self.owner.kernel.GlobalSize.return_value = len(self.data)
        self.owner.kernel.GlobalLock.return_value = ctypes.addressof(self.data)

    @patch('voiceprompt.clipboard.sequence_number', return_value=12)
    def test_windows_rendering_sequence_change_keeps_owned_exact_text(self, sequence):
        self.assertTrue(self.lease.owns())
        self.assertEqual(self.lease.sequence, 12)
        self.owner.user.CloseClipboard.assert_called_once()

    @patch('voiceprompt.clipboard.sequence_number', return_value=12)
    def test_new_clipboard_owner_invalidates_even_identical_text(self, sequence):
        self.owner.user.GetClipboardOwner.return_value = 999
        self.assertFalse(self.lease.owns())
        self.owner.user.OpenClipboard.assert_not_called()

    @patch('voiceprompt.clipboard.sequence_number', return_value=12)
    def test_changed_payload_is_not_pasted_or_restored(self, sequence):
        self.data[0] = b'X'
        self.assertFalse(self.lease.owns())
        self.assertEqual(self.lease.sequence, 10)

    @patch('voiceprompt.clipboard.sequence_number', return_value=12)
    def test_other_new_formats_cannot_be_mistaken_for_system_text_conversion(self, sequence):
        self.owner.user.EnumClipboardFormats.side_effect = [13, 0xC001, 0]
        self.assertFalse(self.lease.owns())

    def test_monitor_read_before_shortcut_does_not_trigger_early_restore(self):
        self.lease.consumed.set()
        self.lease.arm()
        self.assertFalse(self.lease.consumed.is_set())

    def test_published_sequence_is_sampled_after_windows_closes_clipboard(self):
        current = {'sequence': 10}
        self.owner.current = None
        self.owner.user.CloseClipboard.side_effect = lambda: current.update(sequence=12)
        with patch('voiceprompt.clipboard.sequence_number', side_effect=lambda: current['sequence']):
            lease = self.owner.publish('full transcript', ClipboardSnapshot([], 10), 300)
            self.assertEqual(lease.sequence, 12)
            self.assertTrue(lease.owns())
