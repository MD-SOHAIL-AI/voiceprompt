"""Native cache-aware English streaming, driven on the dictation worker."""
from __future__ import annotations

import ctypes as c
import os
import re
import threading
import wave
from pathlib import Path

import numpy as np

from voiceprompt.nemotron_assets import ASSETS, model_file, runtime_directory, sha256_file


WARMUP_SHA256 = "98e635655e7e519f7f2dc12d375d627268e90d2c8a7061bc12c21eea233547a1"
RIGHT_CONTEXT = 6  # 7 * 80 ms = 560 ms; tested on the Ryzen/Radeon laptop.
FEED_SAMPLES = 1600  # 100 ms at 16 kHz, independent of capture callback size.


class _BackendConfig(c.Structure):
    _fields_ = [("size", c.c_size_t), ("gpu", c.c_int32)]


class _ModelConfig(c.Structure):
    _fields_ = [("size", c.c_size_t), ("path", c.c_char_p), ("name", c.c_char_p)]


class _StreamingConfig(c.Structure):
    _fields_ = [("size", c.c_size_t), ("chunk_size", c.c_float), ("left", c.c_float), ("right", c.c_float), ("rnnt_right", c.c_int32)]


class _EndpointingConfig(c.Structure):
    _fields_ = [("size", c.c_size_t), ("enable", c.c_bool), ("vad_based", c.c_bool), ("silence_ms", c.c_int32)]


class _Config(c.Structure):
    _fields_ = [("size", c.c_size_t)] + [(name, c.c_void_p) for name in ("backend", "model", "streaming", "decoder", "vad", "endpointing", "postproc", "diar", "batching")]


class _NativeApi:
    def __init__(self, folder: Path) -> None:
        self._directory = os.add_dll_directory(str(folder))
        try:
            self._library = c.CDLL(str(folder / "nemo_speech_asr_c.dll"))
            self._create = self._bind("create", [c.POINTER(_Config), c.POINTER(c.c_void_p)], c.c_int)
            self.destroy = self._bind("destroy", [c.c_void_p], None)
            self._start = self._bind("streaming_recognize", [c.c_void_p, c.c_void_p, c.POINTER(c.c_void_p)], c.c_int)
            self._push = self._bind("stream_push_f32", [c.c_void_p, c.POINTER(c.c_float), c.c_size_t, c.c_int32], c.c_int)
            self._next = self._bind("stream_next", [c.c_void_p, c.POINTER(c.c_void_p)], c.c_int)
            self._finish = self._bind("stream_finish", [c.c_void_p], c.c_int)
            self.close_stream = self._bind("stream_close", [c.c_void_p], None)
            self._text = self._bind("result_transcript", [c.c_void_p, c.c_size_t], c.c_char_p)
            self._final = self._bind("result_is_final", [c.c_void_p], c.c_bool)
            self.destroy_result = self._bind("result_destroy", [c.c_void_p], None)
            self._last_error = self._bind("last_error", [], c.c_char_p)
        except Exception:
            self._directory.close()
            raise

    def _bind(self, name, args, result):
        function = getattr(self._library, "nemo_speech_asr_" + name)
        function.argtypes = args
        function.restype = result
        return function

    def _check(self, status) -> None:
        if status:
            message = (self._last_error() or b"Unknown native error").decode("utf-8", errors="replace")
            raise RuntimeError(f"Nemotron recognition failed ({status}): {message}")

    def create(self, weights: Path, device: str):
        backend = _BackendConfig(c.sizeof(_BackendConfig), 0 if device == "vulkan" else -1)
        model = _ModelConfig(c.sizeof(_ModelConfig), os.fsencode(weights), None)
        streaming = _StreamingConfig(c.sizeof(_StreamingConfig), .56, 1.92, 1.92, RIGHT_CONTEXT)
        endpointing = _EndpointingConfig(c.sizeof(_EndpointingConfig), False, False, 0)
        config = _Config(c.sizeof(_Config), c.addressof(backend), c.addressof(model), c.addressof(streaming), None, None, c.addressof(endpointing))
        handle = c.c_void_p()
        try:
            self._check(self._create(c.byref(config), c.byref(handle)))
        except Exception:
            if handle.value:
                self.destroy(handle)
            raise
        if not handle.value:
            raise RuntimeError("Nemotron did not create a recognizer.")
        return handle

    def start(self, recognizer):
        handle = c.c_void_p()
        try:
            self._check(self._start(recognizer, None, c.byref(handle)))
        except Exception:
            if handle.value:
                self.close_stream(handle)
            raise
        if not handle.value:
            raise RuntimeError("Nemotron did not create an audio stream.")
        return handle

    def push(self, stream, audio: np.ndarray) -> None:
        self._check(self._push(stream, audio.ctypes.data_as(c.POINTER(c.c_float)), len(audio), 16000))

    def next(self, stream):
        handle = c.c_void_p()
        try:
            self._check(self._next(stream, c.byref(handle)))
        except Exception:
            if handle.value:
                self.destroy_result(handle)
            raise
        return handle if handle.value else None

    def finish(self, stream) -> None:
        self._check(self._finish(stream))

    def final_text(self, result) -> str | None:
        if not self._final(result):
            return None
        text = self._text(result, 0)
        if text is None:
            raise RuntimeError("Nemotron returned an invalid final transcript.")
        return text.decode("utf-8")


_api_instance: _NativeApi | None = None
_api_lock = threading.Lock()


def _get_api() -> _NativeApi:
    # Keep one SDK/DLL search directory for the process lifetime. Model handles
    # are separate and destroyed on close. CPU/Vulkan use the same package to
    # avoid loading conflicting DLLs with identical names when settings change.
    global _api_instance
    with _api_lock:
        if _api_instance is None:
            _api_instance = _NativeApi(runtime_directory())
        return _api_instance


def _warmup_audio() -> np.ndarray:
    path = ASSETS / "nemotron-warmup.wav"
    if not path.is_file() or sha256_file(path) != WARMUP_SHA256:
        raise RuntimeError("Nemotron's bundled speech warmup is missing or damaged. Reinstall VoicePrompt.")
    with wave.open(str(path), "rb") as source:
        if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (16000, 1, 2):
            raise RuntimeError("Nemotron's speech warmup has an invalid audio format.")
        return np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float32) / 32768


class NemotronTranscriber:
    backend_name = "nemotron"
    streaming = True

    def __init__(self, device: str = "vulkan") -> None:
        if device not in {"vulkan", "cpu"}:
            raise ValueError("Nemotron processing must be vulkan or cpu.")
        self.device = device
        self.loaded_model = ""
        self.fallback_reason = ""
        self._api = None
        self._recognizer = None
        self._stream = None
        self._pending = np.empty(0, dtype=np.float32)
        self._final_text: str | None = None
        self._warmed = False

    def preload(self) -> None:
        if self._warmed:
            return
        try:
            speech = _warmup_audio()
            if self._recognizer is None:
                weights = model_file()
                self._api = _get_api()
                try:
                    self._recognizer = self._api.create(weights, self.device)
                except Exception as exc:
                    raise RuntimeError(f"Nemotron could not initialize {self.device}. Check the graphics driver or select CPU/Parakeet in Settings. {exc}") from exc
            # Silence alone leaves nonblank RNNT paths/device kernels cold.
            # Use licensed public speech, without vocabulary hints, then discard
            # each stream so startup text/state cannot leak into dictation.
            for audio in (np.zeros(16000, dtype=np.float32), speech):
                self._start_session()
                self.accept_audio(audio)
                self.finish_session()
            self._warmed = True
            self.loaded_model = f"nemotron-speech-streaming-en-0.6b-q8-{self.device}-560ms"
        except Exception:
            self.close()
            raise

    def begin_session(self, hotwords: str | None = None) -> None:
        # Retain the tested unboosted decoder; final dictionary replacements
        # still apply in the app. Vocabulary boosting needs its own evaluation.
        self.preload()
        try:
            self._start_session()
        except Exception:
            self._warmed = False
            raise

    def _start_session(self) -> None:
        self.abort_session()
        self._stream = self._api.start(self._recognizer)

    def accept_audio(self, audio: np.ndarray) -> None:
        if self._stream is None:
            raise RuntimeError("No active Nemotron session.")
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        try:
            if len(audio):
                self._pending = np.concatenate((self._pending, audio))
                while len(self._pending) >= FEED_SAMPLES:
                    self._push(self._pending[:FEED_SAMPLES])
                    self._pending = self._pending[FEED_SAMPLES:]
        except Exception:
            self._warmed = False
            self.abort_session()
            raise

    def _push(self, audio: np.ndarray) -> None:
        audio = np.ascontiguousarray(audio, dtype=np.float32)
        if not np.isfinite(audio).all():
            raise RuntimeError("Nemotron received invalid microphone samples. Nothing was pasted.")
        self._api.push(self._stream, audio)
        self._drain()

    def _drain(self) -> None:
        while True:
            result = self._api.next(self._stream)
            if result is None:
                return
            try:
                text = self._api.final_text(result)
                if text is not None:
                    self._final_text = text
            finally:
                self._api.destroy_result(result)

    def finish_session(self) -> str:
        if self._stream is None:
            return ""
        try:
            if len(self._pending):
                self._push(self._pending)
                self._pending = np.empty(0, dtype=np.float32)
            self._api.finish(self._stream)
            self._drain()
            if self._final_text is None:
                raise RuntimeError("Nemotron did not finalize the audio stream. Nothing was pasted.")
            return re.sub(r"\s+", " ", self._final_text).strip()
        except Exception:
            self._warmed = False
            raise
        finally:
            self.abort_session()

    def abort_session(self) -> None:
        stream, self._stream = self._stream, None
        self._pending = np.empty(0, dtype=np.float32)
        self._final_text = None
        if stream is not None:
            self._api.close_stream(stream)

    def close(self) -> None:
        try:
            self.abort_session()
        finally:
            recognizer, self._recognizer = self._recognizer, None
            self._warmed = False
            self.loaded_model = ""
            if recognizer is not None:
                self._api.destroy(recognizer)
