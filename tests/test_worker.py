from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock, patch

from voiceprompt.worker import AudioWorkerContext


class AudioWorkerTests(unittest.TestCase):
    @patch("voiceprompt.worker.ctypes.WinDLL", create=True)
    @patch("voiceprompt.worker.sys.platform", "win32")
    def test_existing_com_context_is_balanced_once(self, load):
        library = load.return_value
        library.CoInitializeEx.return_value = 1  # S_FALSE still increments the count.
        context = AudioWorkerContext()
        context.initialize()
        context.initialize()
        context.close()
        context.close()
        library.CoInitializeEx.assert_called_once_with(None, 0)
        library.CoUninitialize.assert_called_once()

    @patch("voiceprompt.worker.ctypes.WinDLL", create=True)
    @patch("voiceprompt.worker.sys.platform", "win32")
    def test_failed_initialization_is_not_uninitialized(self, load):
        library = load.return_value
        library.CoInitializeEx.return_value = -2147417850
        context = AudioWorkerContext()
        with self.assertRaisesRegex(RuntimeError, "0x80010106"):
            context.initialize()
        context.close()
        library.CoUninitialize.assert_not_called()

    def test_context_cannot_be_closed_from_another_thread(self):
        context = AudioWorkerContext()
        context._library = MagicMock()
        context._owner = threading.get_ident() + 1
        with self.assertRaisesRegex(RuntimeError, "owning thread"):
            context.close()
        context._library.CoUninitialize.assert_not_called()
