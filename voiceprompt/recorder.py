from __future__ import annotations

import threading
import time
from collections import deque
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
    blocksize: int = 0
    min_seconds: float = 0.25
    release_grace_seconds: float = 0.18
    microphone: str = ""
    capture_mode: str = "auto"
    retain_audio: bool = True
    max_seconds: float = 300.18


def microphones() -> list[str]:
    return sorted({str(d["name"]) for d in sd.query_devices() if d["max_input_channels"] > 0})


class PushToTalkRecorder:
    def __init__(self, config: RecorderConfig | None = None) -> None:
        self.config = config or RecorderConfig()
        self._stream: sd.InputStream | None = None
        self._frames: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._started_at = 0.0
        self._capturing = False
        self._sample_count = 0
        self.level = 0.0
        self._envelope = deque([0.0] * 32, maxlen=32)
        self._envelope_level = 0.0
        self._envelope_samples = 0
        self.input_overflows = 0
        self.callback_error = ""
        self.sample_rate = self.config.sample_rate
        self.capture_open_seconds = 0.0
        self.input_latency_seconds = 0.0
        self.device_name = ""
        self.host_api = ""
        self.fallback_reason = ""
        self.on_audio_chunk: Callable[[np.ndarray, int], None] | None = None

    @property
    def is_recording(self) -> bool:
        return self._capturing

    def envelope(self) -> list[float]:
        """A bounded audio meter; reading it never consumes recognition frames."""
        with self._lock:
            return list(self._envelope) if self._capturing else [0.0] * 32

    @property
    def capture_failed(self) -> bool:
        return bool(self._capturing and self._stream is not None and not self._stream.active)

    def prepare(self) -> None:
        """Validate start/stop, then leave capture inactive before dictation."""
        if self._stream is not None:
            return
        started = time.perf_counter()
        devices = sd.query_devices()
        hosts = sd.query_hostapis()
        default_index = sd.default.device[0]
        wanted = self.config.microphone
        if not wanted:
            if default_index < 0:
                raise RuntimeError("No default microphone is available. Select a microphone in Settings.")
            wanted = str(devices[default_index]["name"])
        candidates = [
            (i, d, str(hosts[d["hostapi"]]["name"]))
            for i, d in enumerate(devices)
            # MME truncates long names; match its prefix to the full WASAPI name.
            if d["max_input_channels"] > 0 and (
                d["name"] == wanted or (
                    min(len(str(d["name"])), len(wanted)) >= 20
                    and (str(d["name"]).startswith(wanted) or wanted.startswith(str(d["name"])))
                )
            )
        ]
        if self.config.capture_mode == "wasapi":
            candidates = [c for c in candidates if c[2] == "Windows WASAPI"]
        elif self.config.capture_mode == "mme":
            candidates = [c for c in candidates if c[2] == "MME"]
        else:
            candidates.sort(key=lambda c: {"Windows WASAPI": 0, "MME": 1}.get(c[2], 2))
        if not candidates:
            raise RuntimeError(f"Microphone '{wanted}' is unavailable for {self.config.capture_mode}.")
        failures: list[str] = []
        for index, device, host in candidates:
            for rate in dict.fromkeys([self.config.sample_rate, int(device["default_samplerate"])]):
                stream = None
                try:
                    sd.check_input_settings(device=index, samplerate=rate, channels=1, dtype="float32")
                    stream = sd.InputStream(
                        device=index, samplerate=rate, channels=1, dtype="float32",
                        blocksize=self.config.blocksize, latency="low", callback=self._on_audio,
                    )
                    # Opening can succeed even when the driver cannot start.
                    # _capturing remains false: probe frames are never retained.
                    stream.start()
                    stream.stop()
                except Exception as exc:
                    if stream is not None:
                        try:
                            stream.close()
                        except Exception:
                            pass
                    failures.append(f"{host} {rate} Hz: {type(exc).__name__}: {exc}")
                    continue
                self._stream = stream
                self.sample_rate = rate
                self.device_name = str(device["name"])
                self.host_api = host
                self.input_latency_seconds = float(stream.latency)
                self.capture_open_seconds = time.perf_counter() - started
                self.fallback_reason = "; ".join(failures)
                return
        raise RuntimeError("Cannot open microphone. " + "; ".join(failures))

    def start(self) -> None:
        if self._capturing:
            return
        self.prepare()
        with self._lock:
            self._frames = []
            self._sample_count = 0
            self._started_at = time.perf_counter()
            self.input_overflows = 0
            self._envelope.clear()
            self._envelope.extend([0.0] * 32)
            self._envelope_level = self._envelope_samples = 0
            self.callback_error = ""
            self._capturing = True
        try:
            self._stream.start()
        except Exception:
            self.close()
            raise

    def stop(self, *, grace: bool = True, released_at: float | None = None) -> Recording | None:
        stream = self._stream
        if stream is None or not self._capturing:
            return None
        released_at = released_at or time.perf_counter()
        held_seconds = released_at - self._started_at
        # Continue retaining callback frames until the release grace deadline.
        if grace:
            time.sleep(max(0.0, released_at + self.config.release_grace_seconds - time.perf_counter()))
        try:
            stream.stop()
        except Exception:
            self.close()
            raise
        finally:
            with self._lock:
                self._capturing = False

        with self._lock:
            frames = list(self._frames)
            self._frames = []

        if held_seconds < self.config.min_seconds or not self._sample_count:
            return None

        audio = np.concatenate(frames).astype(np.float32, copy=False).reshape(-1) if frames else np.empty(0, dtype=np.float32)
        return Recording(audio=audio, sample_rate=self.sample_rate, duration_seconds=self._sample_count / self.sample_rate)

    def close(self) -> None:
        with self._lock:
            self._capturing = False
            self._frames = []
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.abort()
            finally:
                stream.close()

    def _on_audio(self, indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
        with self._lock:
            if not self._capturing:
                return
            if getattr(status, "input_overflow", False):
                self.input_overflows += 1
            remaining = max(0, round(self.sample_rate * self.config.max_seconds) - self._sample_count)
            chunk = indata[:remaining, 0].copy()
            if not len(chunk):
                return
            self._sample_count += len(chunk)
            self.level = min(1.0, float(np.max(np.abs(chunk))))
            # Keep computation local and bounded. The bridge samples this buffer;
            # no serialization or window operations run on PortAudio's callback.
            self._envelope_samples += len(chunk)
            if self._envelope_samples >= self.sample_rate / 30:
                rms = float(np.sqrt(np.mean(np.square(chunk))))
                target = min(1.0, max(0.0, (rms - 0.003) * 12.0))
                smoothing = 0.72 if target > self._envelope_level else 0.22
                self._envelope_level += smoothing * (target - self._envelope_level)
                self._envelope.append(self._envelope_level)
                self._envelope_samples = 0
            if self.config.retain_audio:
                self._frames.append(chunk)
        if self.on_audio_chunk is not None:
            try:
                self.on_audio_chunk(chunk, self.sample_rate)
            except Exception as exc:
                self.callback_error = f"Audio delivery failed: {type(exc).__name__}: {exc}"
