"""Regression tests for the original main-branch push-to-talk capture."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from voiceprompt.recorder import PushToTalkRecorder


class RecorderGraceTests(unittest.TestCase):
    @patch("voiceprompt.recorder.sd.InputStream")
    def test_release_tail_keeps_final_audio(self, input_stream):
        stream = MagicMock()
        input_stream.return_value = stream
        recorder = PushToTalkRecorder()
        recorder.start()
        # Skip the minimum-length check without recording a real microphone.
        recorder._started_at -= 1.0
        first = np.full((160, 1), 1.0, dtype=np.float32)
        trailing = np.full((160, 1), 2.0, dtype=np.float32)
        recorder._on_audio(first, 160, None, SimpleNamespace())
        with patch("voiceprompt.recorder.time.sleep", side_effect=lambda _: recorder._on_audio(
                trailing, 160, None, SimpleNamespace())):
            recording = recorder.stop()
        np.testing.assert_array_equal(recording.audio[-160:], trailing.ravel())
        self.assertEqual(len(recording.audio), 320)
        self.assertFalse(recorder.is_recording)
        stream.stop.assert_called_once()
        stream.close.assert_called_once()

    @patch("voiceprompt.recorder.sd.InputStream")
    def test_duplicate_stop_does_not_close_stream_twice(self, input_stream):
        stream = MagicMock()
        input_stream.return_value = stream
        recorder = PushToTalkRecorder()
        recorder.start()
        recorder._started_at -= 1.0
        with patch("voiceprompt.recorder.time.sleep", side_effect=lambda _: self.assertIsNone(recorder.stop())):
            self.assertIsNone(recorder.stop())
        stream.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
