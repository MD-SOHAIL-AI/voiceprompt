from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import sounddevice as sd


@dataclass(frozen=True)
class Recording:
    audio: np.ndarray
    sample_rate: int
    duration_seconds: float


@dataclass(frozen=True)
class RecorderConfig:
    sample_rate: int = 16_000
    channels: int = 1
    blocksize: int = 512
    min_seconds: float = 0.25
    release_grace_seconds: float = 0.18


class PushToTalkRecorder:
    def __init__(self, config: RecorderConfig | None = None) -> None:
        self.config = config or RecorderConfig()
        self._stream: sd.InputStream | None = None
        self._frames: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._started_at = 0.0
        self.on_audio_chunk: Callable[[np.ndarray], None] | None = None

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        with self._lock:
            if self._stream is not None:
                return
            self._frames = []
            self._started_at = time.perf_counter()
            self._stream = sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                dtype="float32",
                blocksize=self.config.blocksize,
                callback=self._on_audio,
            )
            self._stream.start()

    def stop(self) -> Recording | None:
        with self._lock:
            stream = self._stream
            self._stream = None
        if stream is None:
            return None

        # Capture the final phoneme after the user releases push-to-talk.
        time.sleep(self.config.release_grace_seconds)
        stream.stop()
        stream.close()

        with self._lock:
            frames = list(self._frames)
            self._frames = []

        duration = time.perf_counter() - self._started_at
        if duration < self.config.min_seconds or not frames:
            return None

        audio = np.concatenate(frames).astype(np.float32, copy=False).reshape(-1)
        return Recording(audio=audio, sample_rate=self.config.sample_rate, duration_seconds=duration)

    def _on_audio(self, indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
        with self._lock:
            if self._stream is not None:
                self._frames.append(indata.copy())
        if self.on_audio_chunk is not None:
            try:
                self.on_audio_chunk(indata)
            except Exception:
                pass
