from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from voiceprompt.audio import AudioProcessor
from voiceprompt.state import FINALIZATION_TIMEOUT_SECONDS, MAX_RECORDING_SECONDS, StopReason

if TYPE_CHECKING:
    from voiceprompt.recorder import PushToTalkRecorder
    from voiceprompt.transcriber import TranscriptionBackend


class IncompleteRecording(RuntimeError):
    pass


class AudioQueue:
    """Duration-bounded buffer. Retained chunks share storage with the reader."""

    def __init__(self, max_seconds: float = MAX_RECORDING_SECONDS + 1, *, retain: bool = False):
        self._chunks = deque()
        self._archive = []
        self._condition = threading.Condition()
        self._seconds = 0.0
        self._total_seconds = 0.0
        self.max_seconds = max_seconds
        self.retain = retain
        self.peak_seconds = 0.0
        self.overflow = False

    @property
    def seconds(self):
        with self._condition:
            return self._seconds

    @property
    def empty(self):
        with self._condition:
            return not self._chunks

    def put(self, audio: np.ndarray, sample_rate: int):
        seconds = len(audio) / sample_rate
        with self._condition:
            if self.overflow:
                return
            used = self._total_seconds if self.retain else self._seconds
            if used + seconds > self.max_seconds + 1e-6:
                self.overflow = True
            else:
                item = (audio, sample_rate)
                self._chunks.append(item)
                if self.retain:
                    self._archive.append(item)
                self._total_seconds += seconds
                self._seconds += seconds
                self.peak_seconds = max(self.peak_seconds, self._seconds)
            self._condition.notify_all()

    def get(self, timeout: float = 0.02):
        with self._condition:
            if not self._chunks and timeout:
                self._condition.wait(timeout)
            if self.overflow:
                raise IncompleteRecording("The recording buffer reached its safety limit. Nothing was pasted.")
            if not self._chunks:
                return None
            audio, rate = self._chunks.popleft()
            self._seconds = max(0, self._seconds - len(audio) / rate)
            return audio, rate

    def retained(self):
        with self._condition:
            return tuple(self._archive)

    def clear(self):
        with self._condition:
            self._chunks.clear()
            self._archive.clear()
            self._seconds = self._total_seconds = 0.0


@dataclass
class DictationSession:
    session_id: int
    audio_queue: AudioQueue = field(default_factory=lambda: AudioQueue(retain=True))
    release: threading.Event = field(default_factory=threading.Event)
    cancel: threading.Event = field(default_factory=threading.Event)
    released_at: float | None = None
    metrics: dict = field(default_factory=dict)
    max_seconds: float = MAX_RECORDING_SECONDS
    finalization_timeout: float = FINALIZATION_TIMEOUT_SECONDS
    stop_reason: StopReason = StopReason.RELEASED
    target_window: int = 0
    phase: str = "starting"
    _release_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def request_release(self, reason: StopReason = StopReason.RELEASED):
        with self._release_lock:
            if not self.release.is_set():
                self.stop_reason = reason
                self.released_at = time.perf_counter()
                self.release.set()

    def run(self, recorder: PushToTalkRecorder, backend: TranscriptionBackend, *, hotwords: str,
            noise_suppression: bool, on_recording_started: Callable | None = None,
            on_recording_stopped: Callable | None = None, on_progress: Callable | None = None):
        """The caller owns capture/COM. Only the decoder thread may block on ASR."""
        processor = None
        decoder = None
        capture_done = threading.Event()
        valid_recording = threading.Event()
        errors, result = [], []
        recording = None
        decoding_seconds = 0.0
        decoded_audio_seconds = 0.0

        def decode():
            nonlocal decoding_seconds, decoded_audio_seconds
            try:
                # Stream creation can stall in native code. Start capture first
                # and keep those initial words in the queue while it completes.
                if self.cancel.is_set():
                    return
                then = time.perf_counter()
                backend.begin_session(hotwords)
                self.metrics["session_setup_seconds"] = time.perf_counter() - then
                self.phase = "recognizing"
                while not self.cancel.is_set():
                    chunk = self.audio_queue.get()
                    if chunk is not None:
                        audio, rate = chunk
                        then = time.perf_counter()
                        processed = processor.process(audio)
                        after_processing = time.perf_counter()
                        self.metrics["preprocessing_seconds"] = self.metrics.get("preprocessing_seconds", 0) + after_processing - then
                        backend.accept_audio(processed)
                        decoding_seconds += time.perf_counter() - then
                        decoded_audio_seconds += len(audio) / rate
                    elif capture_done.is_set() and self.audio_queue.empty:
                        # A callback may enqueue the release tail between an
                        # empty read and capture_done. Recheck under the queue's
                        # lock after observing completion before finalizing.
                        break
                if valid_recording.is_set() and not self.cancel.is_set():
                    self.phase = "finalizing"
                    then = time.perf_counter()
                    backend.accept_audio(processor.process(np.empty(0, dtype=np.float32), final=True))
                    result.append(backend.finish_session())
                    self.metrics["native_finalization_seconds"] = time.perf_counter() - then
                    decoding_seconds += time.perf_counter() - then
            except Exception as exc:
                errors.append(exc)
            finally:
                # The decoder owns processing. Even if interruption outlives
                # the capture thread's join, native denoiser state is released.
                if processor is not None:
                    processor.close()

        try:
            if self.cancel.is_set() or self.release.is_set():
                return "", 0.0
            capture_started = time.perf_counter()
            recorder.prepare()
            processor = AudioProcessor(recorder.sample_rate, noise_suppression)
            recorder.on_audio_chunk = self.audio_queue.put
            if self.cancel.is_set() or self.release.is_set():
                return "", 0.0
            recorder.start()
            self.metrics["capture_start_seconds"] = time.perf_counter() - capture_started
            self._feedback(on_recording_started)
            started = time.perf_counter()
            decoder = threading.Thread(target=decode, name=f"recognition-{self.session_id}", daemon=True)
            decoder.start()
            while not self.release.is_set() and not self.cancel.is_set():
                elapsed = time.perf_counter() - started
                self._check_capture(recorder)
                if elapsed >= self.max_seconds:
                    self.request_release(StopReason.DURATION_LIMIT)
                if on_progress:
                    on_progress(elapsed, self.audio_queue.seconds, bool(errors))
                self.release.wait(0.02)
            if self.cancel.is_set():
                self.request_release(StopReason.CANCELLED)
                raise IncompleteRecording("Recording cancelled.")
            recording = recorder.stop(released_at=self.released_at)
            self.metrics["backlog_at_release_seconds"] = self.audio_queue.seconds
            self._check_capture(recorder)
            self._feedback(on_recording_stopped)
            if recording is not None:
                valid_recording.set()
            capture_done.set()
            deadline = self.released_at + self.finalization_timeout
            self.phase = "draining" if self.audio_queue.seconds else self.phase
            set_deadline = getattr(backend, "set_finalization_deadline", None)
            if callable(set_deadline):
                set_deadline(time.monotonic() + max(0, deadline - time.perf_counter()))
            while decoder.is_alive():
                if self.cancel.is_set() or time.perf_counter() >= deadline:
                    self.stop_reason = StopReason.CANCELLED if self.cancel.is_set() else StopReason.TIMEOUT
                    self._interrupt(backend)
                    raise IncompleteRecording("Recording cancelled." if self.cancel.is_set() else
                                              "Recognition took too long. Your recording is available to retry.")
                if on_progress:
                    on_progress(recording.duration_seconds if recording else 0, self.audio_queue.seconds, bool(errors))
                decoder.join(0.02)
            if errors:
                self.stop_reason = StopReason.RECOGNITION_FAILED
                raise IncompleteRecording(f"Recognition failed ({type(errors[0]).__name__}). Your recording is available to retry.") from errors[0]
            if recording is None:
                backend.abort_session()
                return "", 0.0
            self.metrics["release_to_final_seconds"] = time.perf_counter() - self.released_at
            return result[0] if result else "", recording.duration_seconds
        except Exception:
            self.cancel.set()
            capture_done.set()
            if decoder is not None and decoder.is_alive():
                self._interrupt(backend)
                decoder.join(1)
            if decoder is None or not decoder.is_alive():
                try:
                    backend.abort_session()
                except Exception:
                    pass
            raise
        finally:
            self.phase = "complete"
            recorder.on_audio_chunk = None
            if recorder.is_recording:
                recorder.stop(grace=False)
            if processor is not None and (decoder is None or not decoder.is_alive()):
                processor.close()
            self.metrics.update(
                stop_reason=self.stop_reason.value, decoding_seconds=decoding_seconds,
                decoded_audio_seconds=decoded_audio_seconds,
                recording_seconds=recording.duration_seconds if recording is not None else 0.0,
                processing_ratio=decoding_seconds / max(decoded_audio_seconds, .001),
                queue_peak_seconds=self.audio_queue.peak_seconds, queue_overflow=self.audio_queue.overflow,
                input_overflows=recorder.input_overflows, capture_open_seconds=recorder.capture_open_seconds,
                input_latency_seconds=recorder.input_latency_seconds, capture_host_api=recorder.host_api,
            )

    @staticmethod
    def _interrupt(backend):
        interrupt = getattr(backend, "interrupt", None)
        if callable(interrupt):
            interrupt()

    @staticmethod
    def _feedback(callback):
        if callback is not None:
            try:
                callback()
            except Exception:
                logging.getLogger(__name__).warning("Recording feedback could not be delivered")

    def _check_capture(self, recorder):
        if recorder.capture_failed is True or recorder.callback_error:
            self.stop_reason = StopReason.CAPTURE_FAILED
            self.metrics["capture_failed"] = True
            raise IncompleteRecording("The microphone stopped unexpectedly. Reconnect it and prepare the microphone again.")
        if recorder.input_overflows:
            self.stop_reason = StopReason.CAPTURE_FAILED
            raise IncompleteRecording("The microphone dropped audio frames. Nothing was pasted; try closing other busy applications.")


class ReplayRecorder:
    """Feed one retained recording without opening a microphone or writing audio."""
    input_overflows = 0
    callback_error = ""
    capture_failed = False
    capture_open_seconds = input_latency_seconds = 0.0
    host_api = "memory"
    is_recording = False
    on_audio_chunk = None

    def __init__(self, chunks, session):
        self.chunks, self.session = chunks, session
        self.sample_rate = chunks[0][1]

    def prepare(self):
        pass

    def start(self):
        self.is_recording = True
        for audio, rate in self.chunks:
            self.on_audio_chunk(audio, rate)
        self.session.request_release()

    def stop(self, **kwargs):
        from voiceprompt.recorder import Recording
        self.is_recording = False
        return Recording(np.empty(0, dtype=np.float32), self.sample_rate,
                         sum(len(audio) / rate for audio, rate in self.chunks))
