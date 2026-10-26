from __future__ import annotations

import re
import threading
from typing import Protocol

import numpy as np
from faster_whisper import WhisperModel

from voiceprompt.config import Settings
from voiceprompt.downloads import report_progress


class TranscriptionBackend(Protocol):
    backend_name: str
    streaming: bool
    loaded_model: str
    fallback_reason: str

    def preload(self) -> None: ...
    def begin_session(self, hotwords: str | None = None) -> None: ...
    def accept_audio(self, audio: np.ndarray) -> None: ...
    def finish_session(self) -> str: ...
    def abort_session(self) -> None: ...
    def close(self) -> None: ...


class LocalTranscriber:
    def __init__(
        self,
        model_name: str = "base.en",
        language: str = "en",
        device: str = "cpu",
        compute_type: str = "int8",
        beam_size: int = 3,
        vad_filter: bool = False,
        fallback_model_name: str = "base.en",
        cpu_threads: int = 4,
    ) -> None:
        self.model_name = model_name
        self.language = language or None
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.fallback_model_name = fallback_model_name
        self.cpu_threads = cpu_threads
        self.loaded_model = ""
        self.fallback_reason = ""
        self.backend_name = "whisper"
        self.streaming = False
        self._frames: list[np.ndarray] = []
        self._hotwords: str | None = None
        self._warmed = False
        self._model: WhisperModel | None = None
        self._lock = threading.Lock()

    def preload(self) -> None:
        self._get_model()
        if not self._warmed:
            # Execute decoding once, instead of only mapping weights into memory.
            list(self._model.transcribe(
                np.zeros(16000, dtype=np.float32), language=self.language,
                beam_size=1, temperature=0.0, vad_filter=False,
                without_timestamps=True, condition_on_previous_text=False,
            )[0])
            self._warmed = True

    def begin_session(self, hotwords: str | None = None) -> None:
        self._frames = []
        self._hotwords = hotwords

    def accept_audio(self, audio: np.ndarray) -> None:
        if len(audio):
            self._frames.append(audio)

    def finish_session(self) -> str:
        frames, self._frames = self._frames, []
        if not frames:
            return ""
        return self.transcribe(np.concatenate(frames), self._hotwords)

    def abort_session(self) -> None:
        self._frames = []

    def close(self) -> None:
        self.abort_session()
        self._model = None
        self._warmed = False
        self.loaded_model = ""

    def update_options(self, language: str, beam_size: int, vad_filter: bool) -> None:
        self.language = language or None
        self.beam_size = beam_size
        self.vad_filter = vad_filter

    def transcribe(self, audio: np.ndarray, hotwords: str | None = None) -> str:
        model = self._get_model()
        vocabulary_prompt = f"Technical dictation. Vocabulary: {hotwords}." if hotwords else None
        segments, _ = model.transcribe(
            audio,
            language=self.language,
            beam_size=self.beam_size,
            temperature=0.0,
            vad_filter=self.vad_filter,
            vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 200},
            condition_on_previous_text=False,
            without_timestamps=True,
            initial_prompt=vocabulary_prompt,
            hotwords=hotwords or None,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return re.sub(r"\s+", " ", text)

    def _get_model(self) -> WhisperModel:
        with self._lock:
            if self._model is None:
                try:
                    self._model = self._load_model(self.model_name)
                    self.loaded_model = self.model_name
                    self.fallback_reason = ""
                except Exception as exc:
                    if self.model_name == self.fallback_model_name:
                        raise
                    self.fallback_reason = f"{self.model_name} could not load: {type(exc).__name__}: {exc}"
                    self._model = self._load_model(self.fallback_model_name)
                    self.loaded_model = self.fallback_model_name
            return self._model

    def _load_model(self, model_name: str) -> WhisperModel:
        return WhisperModel(
            model_name,
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
        )


class MoonshineTranscriber:
    """English quantized streaming models, with one native stream per session."""

    backend_name = "moonshine"
    streaming = True

    def __init__(self, model_name: str = "tiny") -> None:
        if model_name not in {"tiny", "small"}:
            raise ValueError("Moonshine model must be tiny or small.")
        self.model_name = model_name
        self.loaded_model = ""
        self.fallback_reason = ""
        self._model = None
        self._stream = None
        self._warmed = False
        self._lines: dict[int, str] = {}
        self._stream_error = ""
        self._pending = np.empty(0, dtype=np.float32)

    def preload(self) -> None:
        if self._model is None:
            from moonshine_voice import ModelArch, Transcriber, get_model_for_language

            arch = ModelArch.SMALL_STREAMING if self.model_name == "small" else ModelArch.TINY_STREAMING
            model_path, arch = get_model_for_language(
                wanted_language="en", wanted_model_arch=arch,
                on_progress=lambda fraction, filename: report_progress(
                    {"phase": "Downloading Moonshine model", "name": filename, "completed": fraction, "total": 1}),
            )
            self._model = Transcriber(model_path, arch, update_interval=0.5, options={"return_audio_data": "false"})
            self.loaded_model = f"{self.model_name}-streaming-en"
        if not self._warmed:
            self.begin_session()
            self.accept_audio(np.zeros(16000, dtype=np.float32))
            self.finish_session()
            self._warmed = True

    def begin_session(self, hotwords: str | None = None) -> None:
        if self._model is None:
            self.preload()
        self.abort_session()
        self._lines = {}
        self._stream_error = ""
        if hasattr(self._model, "set_keyterms"):
            self._model.set_keyterms([s.strip() for s in (hotwords or "").split(",") if s.strip()])
        elif hotwords:
            raise RuntimeError("This Moonshine version lacks vocabulary hints. Install the pinned requirements.")
        self._stream = self._model.create_stream(update_interval=0.5)
        self._stream.add_listener(self._on_event)
        self._stream.start()

    def _on_event(self, event: object) -> None:
        from moonshine_voice import Error

        if isinstance(event, Error):
            self._stream_error = f"Moonshine stream failed: {event}"
            return
        line = getattr(event, "line", None)
        if line is not None:
            self._lines[line.line_id] = line.text

    def accept_audio(self, audio: np.ndarray) -> None:
        if self._stream is None:
            raise RuntimeError("No active transcription session.")
        if len(audio):
            self._pending = np.concatenate((self._pending, audio))
            # WASAPI can deliver 10 ms blocks. Amortize native frontend overhead
            # over 100 ms instead of running inference once for every callback.
            while len(self._pending) >= 1600:
                chunk, self._pending = self._pending[:1600], self._pending[1600:]
                self._feed(chunk)

    def _feed(self, audio: np.ndarray) -> None:
        self._stream.add_audio(audio.tolist(), 16000)
        if self._stream_error:
            raise RuntimeError(self._stream_error)

    def finish_session(self) -> str:
        if self._stream is None:
            return ""
        if len(self._pending):
            self._feed(self._pending)
            self._pending = np.empty(0, dtype=np.float32)
        stream, self._stream = self._stream, None
        try:
            transcript = stream.stop()
            if self._stream_error:
                raise RuntimeError(self._stream_error)
            if transcript is None:
                raise RuntimeError("Moonshine did not finalize the audio stream.")
            for line in transcript.lines:
                self._lines[line.line_id] = line.text
            return re.sub(r"\s+", " ", " ".join(self._lines.values())).strip()
        finally:
            stream.close()

    def abort_session(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.close()
        self._lines = {}
        self._pending = np.empty(0, dtype=np.float32)

    def close(self) -> None:
        self.abort_session()
        model, self._model = self._model, None
        if model is not None:
            model.close()
        self._warmed = False
        self.loaded_model = ""


def create_transcriber(settings: Settings) -> TranscriptionBackend:
    if settings.backend == "nemotron":
        from voiceprompt.nemotron_process import NemotronProcessTranscriber

        return NemotronProcessTranscriber(device=settings.nemotron_device)
    if settings.backend == "parakeet":
        from voiceprompt.parakeet import ParakeetTranscriber

        return ParakeetTranscriber(cpu_threads=settings.cpu_threads)
    if settings.backend == "moonshine":
        return MoonshineTranscriber(settings.streaming_model)
    return LocalTranscriber(
        model_name=settings.model, language=settings.language, device=settings.device,
        compute_type=settings.compute_type, beam_size=settings.beam_size,
        vad_filter=settings.vad_filter, cpu_threads=settings.cpu_threads,
    )
