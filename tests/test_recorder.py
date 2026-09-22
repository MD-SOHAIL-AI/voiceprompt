from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from voiceprompt.recorder import PushToTalkRecorder, RecorderConfig


class FakeStream:
    def __init__(self, *args, callback=None, **kwargs):
        self.callback = callback
    def start(self):
        pass
    def stop(self):
        pass
    def close(self):
        pass


class RecorderTests(unittest.TestCase):
    @patch("voiceprompt.recorder.sd.InputStream", FakeStream)
    def test_release_grace_keeps_accepting_final_audio(self) -> None:
        recorder = PushToTalkRecorder(RecorderConfig(min_seconds=0.0, release_grace_seconds=0.01))
        recorder.start()
        recorder._on_audio(np.ones((8, 1), dtype=np.float32), 8, None, None)

        def grace(_seconds: float) -> None:
            recorder._on_audio(np.full((8, 1), 0.5, dtype=np.float32), 8, None, None)

        with patch("voiceprompt.recorder.time.sleep", side_effect=grace):
            result = recorder.stop()
        self.assertIsNotNone(result)
        self.assertEqual(result.audio.size, 16)


if __name__ == "__main__":
    unittest.main()
