from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from voiceprompt.config import Settings
from voiceprompt.parakeet import ParakeetTranscriber, model_files, vad_file
from voiceprompt.transcriber import create_transcriber


class FakeDetector:
    def __init__(self):
        self.segments = deque()
        self.final = None

    def accept_waveform(self, audio):
        pass

    def empty(self):
        return not self.segments

    @property
    def front(self):
        return self.segments[0]

    def pop(self):
        self.segments.popleft()

    def flush(self):
        if self.final is not None:
            self.segments.append(self.final)
            self.final = None

    def reset(self):
        self.segments.clear()
        self.final = None


class ParakeetTests(unittest.TestCase):
    def ready_backend(self):
        backend = ParakeetTranscriber()
        backend._recognizer = MagicMock()
        backend._vad = FakeDetector()
        backend._warmed = True
        return backend

    def test_completed_phrases_decode_before_release_and_tail_is_included_once(self):
        backend = self.ready_backend()
        backend.begin_session("Optional dictionary names")
        backend._vad.segments.append(SimpleNamespace(start=0, samples=np.ones(1600)))
        backend._vad.final = SimpleNamespace(start=1600, samples=np.ones(800))
        with patch.object(backend, "_decode", side_effect=["First phrase.", "Last word."]) as decode:
            backend.accept_audio(np.ones(1600))
            self.assertEqual(decode.call_count, 1)
            backend.accept_audio(np.ones(800))
            self.assertEqual(backend.finish_session(), "First phrase. Last word.")
            self.assertEqual(decode.call_count, 2)
            self.assertEqual(backend.finish_session(), "")
        backend.begin_session()
        self.assertEqual(backend.finish_session(), "")

    def test_failed_tail_never_returns_earlier_partial_transcript(self):
        backend = self.ready_backend()
        backend.begin_session()
        backend._texts.append("Must not paste partial.")
        backend._samples_seen = 800
        backend._history.append((0, np.ones(800)))
        backend._vad.final = SimpleNamespace(start=0, samples=np.ones(800))
        with patch.object(backend, "_decode", side_effect=RuntimeError("decoder failed")):
            with self.assertRaisesRegex(RuntimeError, "decoder failed"):
                backend.finish_session()
        self.assertEqual(backend._texts, [])
        self.assertFalse(backend._active)

    def test_cancel_discards_completed_phrases_and_releases_model(self):
        backend = self.ready_backend()
        backend.begin_session()
        backend._texts.append("cancelled")
        backend.abort_session()
        self.assertEqual(backend.finish_session(), "")
        backend.close()
        self.assertIsNone(backend._recognizer)
        self.assertIsNone(backend._vad)

    def test_factory_selects_parakeet_without_loading_or_downloading(self):
        backend = create_transcriber(Settings(backend="parakeet", cpu_threads=2))
        self.assertIsInstance(backend, ParakeetTranscriber)
        self.assertEqual(backend.cpu_threads, 2)
        self.assertIsNone(backend._recognizer)

    def test_detector_leading_context_preserves_quiet_first_syllables(self):
        backend = self.ready_backend()
        backend.begin_session()
        audio = np.arange(6400, dtype=np.float32)
        backend.accept_audio(audio)
        backend._vad.segments.append(SimpleNamespace(start=3200, samples=audio[3200:4000]))
        with patch.object(backend, "_decode", return_value="It was.") as decode:
            backend.accept_audio(np.zeros(160))
        np.testing.assert_array_equal(decode.call_args.args[0], audio[:4000])

    def test_silence_history_stays_bounded(self):
        backend = self.ready_backend()
        backend.begin_session()
        backend.accept_audio(np.zeros(30 * 16000))
        self.assertEqual(sum(len(chunk) for _, chunk in backend._history), 12 * 16000)

    def test_incomplete_cached_model_is_repaired_before_native_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "encoder.int8.onnx"
            file.write_bytes(b"bad")

            def download(*args, **kwargs):
                if kwargs.get("force_download"):
                    file.write_bytes(b"good")
                return str(file)

            with patch("voiceprompt.parakeet.MODEL_FILES", {file.name: 4}), patch("huggingface_hub.hf_hub_download", side_effect=download) as fetch:
                self.assertEqual(model_files()[file.name].read_bytes(), b"good")
                self.assertTrue(fetch.call_args.kwargs["force_download"])

    def test_invalid_vad_download_is_rejected_and_temporary_file_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("voiceprompt.parakeet.config_dir", return_value=root), patch("voiceprompt.parakeet.urllib.request.urlopen", return_value=io.BytesIO(b"wrong model")):
                with self.assertRaisesRegex(RuntimeError, "checksum"):
                    vad_file()
            self.assertEqual(list((root / "models").iterdir()), [])

    def test_valid_detector_cache_needs_no_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "models" / "silero_vad.onnx"
            model.parent.mkdir()
            model.write_bytes(b"known cached model")
            digest = hashlib.sha256(model.read_bytes()).hexdigest()
            with patch("voiceprompt.parakeet.config_dir", return_value=root), patch("voiceprompt.parakeet.VAD_SHA256", digest), patch("voiceprompt.parakeet.urllib.request.urlopen") as network:
                self.assertEqual(vad_file(), model)
                network.assert_not_called()
