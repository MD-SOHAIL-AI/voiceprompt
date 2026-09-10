from __future__ import annotations

import re
import threading

import numpy as np
from faster_whisper import WhisperModel


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
    ) -> None:
        self.model_name = model_name
        self.language = language or None
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.fallback_model_name = fallback_model_name
        self._model: WhisperModel | None = None
        self._lock = threading.Lock()

    def preload(self) -> None:
        self._get_model()

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
                except Exception:
                    if self.model_name == self.fallback_model_name:
                        raise
                    self._model = self._load_model(self.fallback_model_name)
            return self._model

    def _load_model(self, model_name: str) -> WhisperModel:
        return WhisperModel(
            model_name,
            device=self.device,
            compute_type=self.compute_type,
        )
