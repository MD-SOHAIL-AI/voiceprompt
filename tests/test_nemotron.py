from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import tempfile
import unittest
import zipfile
from collections import deque
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from voiceprompt.config import Settings
from voiceprompt.nemotron import NemotronTranscriber
from voiceprompt.nemotron_process import NemotronProcessTranscriber
from voiceprompt import nemotron_assets as assets
from voiceprompt.transcriber import create_transcriber


class ProcessIsolationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        mock = patch("voiceprompt.nemotron_process.config_dir", return_value=Path(directory.name))
        mock.start()
        self.addCleanup(mock.stop)
        self.backend = NemotronProcessTranscriber()
        self.connection = Mock()
        self.connection.poll.return_value = True
        self.connection.recv.return_value = (True, None, "warmed-model")
        self.process = Mock()
        self.process.poll.return_value = 0
        self.backend._connection = self.connection
        self.backend._process = self.process
        self.backend.loaded_model = "warmed-model"
        self.backend._active = True
        self.addCleanup(self.backend.close)

    def test_batches_pipe_audio_and_flushes_remainder_once(self):
        audio = np.arange(3207, dtype=np.float32)
        self.backend.accept_audio(audio[:71])
        self.backend.accept_audio(audio[71:])
        self.connection.recv.return_value = (True, "complete dictation", "warmed-model")
        self.assertEqual(self.backend.finish_session(), "complete dictation")
        commands = [call.args[0] for call in self.connection.send.call_args_list]
        self.assertEqual([command[0] for command in commands], ["audio", "audio", "audio", "finish"])
        np.testing.assert_array_equal(np.concatenate([command[1] for command in commands[:3]]), audio)
        self.assertEqual(self.backend.finish_session(), "")

    def test_cancellation_discards_audio_before_sending_abort(self):
        self.backend.accept_audio(np.ones(70, dtype=np.float32))
        self.backend.abort_session()
        self.backend.abort_session()
        self.connection.send.assert_called_once_with(("abort", None))
        self.assertEqual(self.backend.finish_session(), "")

    def test_native_failure_invalidates_session_and_loaded_model(self):
        self.connection.recv.return_value = (False, "native failure", "")
        with self.assertRaisesRegex(RuntimeError, "native failure"):
            self.backend.accept_audio(np.ones(1600, dtype=np.float32))
        self.assertEqual(self.backend.loaded_model, "")
        self.assertEqual(self.backend.finish_session(), "")
        self.connection.close.assert_called_once()

    def test_worker_timeout_stops_process_and_discards_pending_audio(self):
        self.connection.poll.return_value = False
        self.process.wait.side_effect = [subprocess.TimeoutExpired("worker", .2), None]
        with self.assertRaisesRegex(RuntimeError, "stopped responding"):
            self.backend.accept_audio(np.ones(1600, dtype=np.float32))
        self.process.terminate.assert_called_once()
        self.assertEqual(self.backend.finish_session(), "")

    def test_abrupt_native_process_exit_does_not_terminate_parent(self):
        self.backend.close()
        with patch("voiceprompt.nemotron_process._worker_command", return_value=[sys.executable, "-c", "import os; os._exit(23)"]):
            self.backend._start_worker()
        with self.assertRaisesRegex(RuntimeError, "native worker stopped"):
            self.backend._exchange("preload", timeout=15)
        self.assertIsNone(self.backend._process)
        self.assertEqual(self.backend.loaded_model, "")
        self.assertEqual(self.backend.finish_session(), "")


class FakeApi:
    def __init__(self):
        self.streams = []
        self.destroyed = []
        self.closed = []
        self.destroyed_results = []
        self.delivered_results = []
        self.texts = deque(["warmup silence", "warmup speech", " complete   dictation "])
        self.fail_finish = False
        self.missing_final = False
        self.fail_push = False

    def create(self, weights, device):
        self.device = device
        return "recognizer"

    def start(self, recognizer):
        stream = {"chunks": [], "results": deque()}
        self.streams.append(stream)
        return stream

    def push(self, stream, audio):
        if self.fail_push:
            raise RuntimeError("native push failed")
        stream["chunks"].append(audio.copy())
        stream["results"].append({"final": False, "text": "partial must never be returned"})

    def next(self, stream):
        if not stream["results"]:
            return None
        result = stream["results"].popleft()
        self.delivered_results.append(result)
        return result

    def final_text(self, result):
        return result["text"] if result["final"] else None

    def finish(self, stream):
        if self.fail_finish:
            raise RuntimeError("native finalization failed")
        if not self.missing_final:
            stream["results"].append({"final": True, "text": self.texts.popleft() if self.texts else ""})

    def close_stream(self, stream):
        self.closed.append(stream)

    def destroy_result(self, result):
        self.destroyed_results.append(result)

    def destroy(self, recognizer):
        self.destroyed.append(recognizer)


class NemotronTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi()
        for name, value in (("_get_api", self.api), ("model_file", Path("model.gguf")), ("_warmup_audio", np.ones(3200, dtype=np.float32))):
            mock = patch("voiceprompt.nemotron." + name, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)
        self.backend = NemotronTranscriber()
        self.addCleanup(self.backend.close)

    def test_factory_is_lazy_and_uses_explicit_device(self):
        with patch("voiceprompt.nemotron._get_api") as native:
            backend = create_transcriber(Settings(backend="nemotron", nemotron_device="cpu"))
        self.assertIsInstance(backend, NemotronProcessTranscriber)
        self.assertEqual(backend.device, "cpu")
        native.assert_not_called()

    def test_warmup_is_once_and_its_text_never_leaks_into_dictation(self):
        self.backend.preload()
        self.backend.preload()
        self.assertEqual(len(self.api.streams), 2)
        self.assertEqual(len(self.api.closed), 2)
        self.backend.begin_session("MyProject")
        audio = np.arange(6414, dtype=np.float64)[::2]
        self.backend.accept_audio(audio)
        self.assertEqual(self.backend.finish_session(), "complete dictation")
        stream = self.api.streams[-1]
        np.testing.assert_array_equal(np.concatenate(stream["chunks"]), audio)
        self.assertEqual([len(a) for a in stream["chunks"]], [1600, 1600, 7])
        self.assertTrue(all(a.dtype == np.float32 and a.flags.c_contiguous for a in stream["chunks"]))
        self.assertEqual(self.api.destroyed_results, self.api.delivered_results)

    def test_cancel_discards_pending_audio_and_does_not_finalize(self):
        self.backend.begin_session()
        self.backend.accept_audio(np.ones(47, dtype=np.float32))
        cancelled = self.api.streams[-1]
        self.backend.abort_session()
        self.backend.abort_session()
        self.assertEqual(cancelled["chunks"], [])
        self.backend.begin_session()
        self.api.texts = deque([""])
        self.assertEqual(self.backend.finish_session(), "")
        self.assertEqual(self.api.streams[-1]["chunks"], [])

    def test_interim_is_discarded_when_final_is_missing(self):
        self.backend.begin_session()
        self.backend.accept_audio(np.ones(1600, dtype=np.float32))
        self.api.missing_final = True
        with self.assertRaisesRegex(RuntimeError, "did not finalize"):
            self.backend.finish_session()
        self.assertIsNone(self.backend._stream)
        self.assertFalse(self.backend._warmed)

    def test_empty_final_overrides_interim_speech(self):
        self.backend.begin_session()
        self.backend.accept_audio(np.ones(1600, dtype=np.float32))
        self.api.texts = deque([""])
        self.assertEqual(self.backend.finish_session(), "")

    def test_native_failure_closes_stream_and_requires_warmup_again(self):
        self.backend.begin_session()
        self.api.fail_finish = True
        with self.assertRaisesRegex(RuntimeError, "finalization failed"):
            self.backend.finish_session()
        self.assertIsNone(self.backend._stream)
        self.assertFalse(self.backend._warmed)
        self.assertEqual(len(self.api.closed), 3)

    def test_push_failure_discards_partial_output(self):
        self.backend.begin_session()
        self.api.fail_push = True
        with self.assertRaisesRegex(RuntimeError, "push failed"):
            self.backend.accept_audio(np.ones(1600, dtype=np.float32))
        self.assertIsNone(self.backend._stream)
        self.assertFalse(self.backend._warmed)
        self.assertEqual(self.backend.finish_session(), "")

    def test_warmup_failure_is_not_ready_and_frees_recognizer(self):
        self.api.fail_finish = True
        with self.assertRaises(RuntimeError):
            self.backend.preload()
        self.assertFalse(self.backend._warmed)
        self.assertEqual(self.backend.loaded_model, "")
        self.assertEqual(self.api.destroyed, ["recognizer"])

    def test_close_is_idempotent_and_destroys_model_once(self):
        self.backend.begin_session()
        self.backend.close()
        self.backend.close()
        self.assertEqual(self.api.destroyed, ["recognizer"])
        self.assertEqual(len(self.api.closed), 3)


class NemotronAssetTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.asset_dir = self.root / "assets"
        self.asset_dir.mkdir()
        self.dll = b"verified test binary"
        self.hashes = {"nemo_speech_asr_c.dll": hashlib.sha256(self.dll).hexdigest()}
        import json
        (self.asset_dir / "nemotron-runtime-hashes.json").write_text(json.dumps(self.hashes))
        for name, value in (("config_dir", self.root), ("ASSETS", self.asset_dir)):
            mock = patch.object(assets, name, value) if name == "ASSETS" else patch.object(assets, name, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)
        mock = patch.object(assets.sysconfig, "get_platform", return_value="win-amd64")
        mock.start()
        self.addCleanup(mock.stop)

    def archive(self, entries):
        folder = self.root / "runtimes"
        folder.mkdir(exist_ok=True)
        path = folder / f"{assets.RUNTIME_NAME}.zip"
        with zipfile.ZipFile(path, "w") as output:
            for name, content in entries.items():
                output.writestr(name, content)
        return path

    def test_verified_install_is_reused_without_network_or_archive(self):
        folder = self.root / "runtimes" / assets.RUNTIME_NAME / "bin"
        folder.mkdir(parents=True)
        (folder / "nemo_speech_asr_c.dll").write_bytes(self.dll)
        with patch.object(assets.urllib.request, "urlopen") as network:
            self.assertEqual(assets.runtime_directory(), folder)
        network.assert_not_called()

    def test_corrupt_binary_is_repaired_from_verified_cached_archive(self):
        path = self.archive({f"{assets.RUNTIME_NAME}/bin/nemo_speech_asr_c.dll": self.dll})
        folder = self.root / "runtimes" / assets.RUNTIME_NAME / "bin"
        folder.mkdir(parents=True)
        (folder / "nemo_speech_asr_c.dll").write_bytes(b"bad")
        with patch.object(assets, "RUNTIME_SHA256", assets.sha256_file(path)), patch.object(assets.urllib.request, "urlopen") as network:
            self.assertEqual(assets.runtime_directory(), folder)
        self.assertEqual((folder / "nemo_speech_asr_c.dll").read_bytes(), self.dll)
        network.assert_not_called()

    def test_invalid_download_is_rejected_before_native_install(self):
        with patch.object(assets.urllib.request, "urlopen", return_value=io.BytesIO(b"wrong archive")):
            with self.assertRaisesRegex(RuntimeError, "checksum"):
                assets.runtime_directory()
        self.assertFalse((self.root / "runtimes" / assets.RUNTIME_NAME).exists())

    def test_archive_paths_cannot_escape_install_staging(self):
        path = self.archive({"../../outside.dll": b"escape"})
        with patch.object(assets, "RUNTIME_SHA256", assets.sha256_file(path)):
            with self.assertRaisesRegex(RuntimeError, "Unsafe path"):
                assets.runtime_directory()

    def test_model_checks_content_and_repairs_same_size_corruption(self):
        path = self.root / "model.gguf"
        path.write_bytes(b"bad!")
        def download(*args, **kwargs):
            if kwargs.get("force_download"):
                path.write_bytes(b"good")
            return str(path)
        with patch.object(assets, "MODEL_BYTES", 4), patch.object(assets, "MODEL_SHA256", hashlib.sha256(b"good").hexdigest()), patch("huggingface_hub.hf_hub_download", side_effect=download) as fetch:
            self.assertEqual(assets.model_file(), path)
        self.assertEqual(fetch.call_count, 2)
        self.assertTrue(fetch.call_args.kwargs["force_download"])


if __name__ == "__main__":
    unittest.main()
