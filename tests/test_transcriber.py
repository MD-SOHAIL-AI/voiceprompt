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
        self.instances.append(self)

    def transcribe(self, audio: np.ndarray, **kwargs: object):
        self.calls.append(kwargs)
        return iter([SimpleNamespace(text="  hello   ChatGPT ")]), None


class LocalTranscriberTests(unittest.TestCase):
    @patch("voiceprompt.transcriber.WhisperModel", FakeWhisperModel)
    def test_option_updates_reuse_model_and_bias_vocabulary(self) -> None:
        FakeWhisperModel.instances.clear()
        transcriber = LocalTranscriber(beam_size=3, vad_filter=True)
        transcriber.preload()
        transcriber.update_options("en", beam_size=1, vad_filter=False)

        text = transcriber.transcribe(np.zeros(1600, dtype=np.float32), hotwords="ChatGPT")

        self.assertEqual(text, "hello ChatGPT")
        self.assertEqual(len(FakeWhisperModel.instances), 1)
        call = FakeWhisperModel.instances[0].calls[-1]
        self.assertEqual(call["beam_size"], 1)
        self.assertEqual(call["temperature"], 0.0)
        self.assertEqual(call["hotwords"], "ChatGPT")
        self.assertIn("Vocabulary: ChatGPT", call["initial_prompt"])
        self.assertFalse(call["vad_filter"])

    @patch("voiceprompt.transcriber.WhisperModel", FakeWhisperModel)
    def test_warmup_executes_once_and_session_audio_is_cleared(self) -> None:
        FakeWhisperModel.instances.clear()
        transcriber = LocalTranscriber(cpu_threads=2)
        transcriber.preload()
        transcriber.preload()
        self.assertEqual(len(FakeWhisperModel.instances[0].calls), 1)
        transcriber.begin_session("MyProject")
        transcriber.accept_audio(np.ones(3200, dtype=np.float32))
        self.assertEqual(transcriber.finish_session(), "hello ChatGPT")
        transcriber.begin_session()
        self.assertEqual(transcriber.finish_session(), "")

    def test_model_failure_reports_actual_fallback(self) -> None:
        with patch("voiceprompt.transcriber.WhisperModel", side_effect=[RuntimeError("missing model.bin"), FakeWhisperModel()]):
            transcriber = LocalTranscriber(model_name="broken")
            transcriber.preload()
        self.assertEqual(transcriber.loaded_model, "base.en")
        self.assertIn("missing model.bin", transcriber.fallback_reason)


if __name__ == "__main__":
    unittest.main()
