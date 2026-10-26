from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from voiceprompt.transcriber import MoonshineTranscriber


class MoonshineTests(unittest.TestCase):
    def backend(self):
        backend = MoonshineTranscriber("tiny")
        native = MagicMock()
        stream = native.create_stream.return_value
        stream.stop.return_value = SimpleNamespace(lines=[
            SimpleNamespace(line_id=1, text="hello world"),
            SimpleNamespace(line_id=2, text="second phrase"),
        ])
        backend._model = native
        return backend, native, stream

    def test_native_chunks_are_batched_and_final_remainder_is_preserved(self):
        backend, native, stream = self.backend()
        backend.begin_session("MyProject, OpenRouter")
        native.set_keyterms.assert_called_once_with(["MyProject", "OpenRouter"])
        backend.accept_audio(np.ones(800, dtype=np.float32))
        stream.add_audio.assert_not_called()
        backend.accept_audio(np.ones(1000, dtype=np.float32))
        self.assertEqual(len(stream.add_audio.call_args.args[0]), 1600)
        self.assertEqual(backend.finish_session(), "hello world second phrase")
        self.assertEqual([len(c.args[0]) for c in stream.add_audio.call_args_list], [1600, 200])
        stream.stop.assert_called_once()
        stream.close.assert_called_once()

    def test_partial_revision_does_not_duplicate_words_and_sessions_reset(self):
        backend, native, stream = self.backend()
        backend.begin_session()
        backend._on_event(SimpleNamespace(line=SimpleNamespace(line_id=1, text="hello")))
        backend._on_event(SimpleNamespace(line=SimpleNamespace(line_id=1, text="hello world")))
        backend._on_event(SimpleNamespace(line=SimpleNamespace(line_id=2, text="second phrase")))
        self.assertEqual(backend.finish_session(), "hello world second phrase")
        stream.stop.return_value = SimpleNamespace(lines=[])
        backend.begin_session()
        self.assertEqual(backend.finish_session(), "")

    def test_stream_error_cannot_return_partial_text(self):
        from moonshine_voice import Error

        backend, native, stream = self.backend()
        backend.begin_session()
        backend._on_event(Error(line=None, stream_handle=1, error=RuntimeError("native failure")))
        with self.assertRaisesRegex(RuntimeError, "native failure"):
            backend.accept_audio(np.ones(1600, dtype=np.float32))
        backend.abort_session()
        stream.close.assert_called_once()

    def test_missing_finalization_is_not_treated_as_success(self):
        backend, native, stream = self.backend()
        backend.begin_session()
        stream.stop.return_value = None
        with self.assertRaisesRegex(RuntimeError, "finalize"):
            backend.finish_session()
        stream.close.assert_called_once()
