from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from voiceprompt.transcriber import LocalTranscriber


class FakeWhisperModel:
    instances: list["FakeWhisperModel"] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.calls: list[dict[str, object]] = []
        self.args = args
        self.instances.append(self)

    def transcribe(self, audio: np.ndarray, **kwargs: object):
        self.calls.append(kwargs)
        return iter([SimpleNamespace(text="  hello   ChatGPT ")]), None


class LocalTranscriberTests(unittest.TestCase):
    @patch("voiceprompt.transcriber.WhisperModel", FakeWhisperModel)
    def test_auto_uses_multilingual_faster_whisper_and_reuses_model(self) -> None:
        FakeWhisperModel.instances.clear()
        transcriber = LocalTranscriber(model_name="base", language="", beam_size=3, vad_filter=True)
        transcriber.preload()
        transcriber.update_options("", beam_size=1, vad_filter=False)
        text = transcriber.transcribe(np.zeros(1600, dtype=np.float32), hotwords="ChatGPT")

        self.assertEqual(text, "hello ChatGPT")
        self.assertEqual(transcriber.engine_name, "faster-whisper")
        self.assertEqual(len(FakeWhisperModel.instances), 1)
        self.assertEqual(FakeWhisperModel.instances[0].args[0], "base")
        call = FakeWhisperModel.instances[0].calls[0]
        self.assertIsNone(call["language"])
        self.assertEqual(call["beam_size"], 1)
        self.assertEqual(call["hotwords"], "ChatGPT")


if __name__ == "__main__":
    unittest.main()
