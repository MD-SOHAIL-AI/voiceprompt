from __future__ import annotations

import re
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel


class FasterWhisperTranscriber:
    engine_name = "faster-whisper"

    def __init__(self, model_name: str = "base", language: str = "", device: str = "cpu", compute_type: str = "int8", beam_size: int = 3, vad_filter: bool = True, fallback_model_name: str = "base") -> None:
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
        return WhisperModel(model_name, device=self.device, compute_type=self.compute_type)


class WhisperCppTranscriber:
    engine_name = "whisper.cpp"

    def __init__(self, executable: str, model_path: str, language: str = "", threads: int = 4) -> None:
        self.executable = Path(executable).expanduser()
        self.model_path = Path(model_path).expanduser()
        self.language = language or "auto"
        self.threads = max(1, int(threads))

    def preload(self) -> None:
        self._validate()

    def update_options(self, language: str, beam_size: int, vad_filter: bool) -> None:
        self.language = language or "auto"

    def transcribe(self, audio: np.ndarray, hotwords: str | None = None) -> str:
        self._validate()
        with tempfile.TemporaryDirectory(prefix="voiceprompt-") as directory:
            root = Path(directory)
            wav_path = root / "speech.wav"
            output_prefix = root / "transcript"
            self._write_wav(wav_path, audio)
            cmd = [
                str(self.executable), "-m", str(self.model_path), "-f", str(wav_path),
                "-l", self.language, "-t", str(self.threads), "-nt", "-otxt", "-of", str(output_prefix),
            ]
            if hotwords:
                cmd.extend(["-p", f"Technical dictation. Vocabulary: {hotwords}."])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=False)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or f"whisper.cpp exited with code {result.returncode}")
            txt_path = output_prefix.with_suffix(".txt")
            text = txt_path.read_text(encoding="utf-8") if txt_path.exists() else result.stdout
            return re.sub(r"\s+", " ", text).strip()

    def _validate(self) -> None:
        if not self.executable.is_file():
            raise FileNotFoundError(f"whisper.cpp executable not found: {self.executable}")
        if not self.model_path.is_file():
            raise FileNotFoundError(f"whisper.cpp model not found: {self.model_path}")

    @staticmethod
    def _write_wav(path: Path, audio: np.ndarray) -> None:
        pcm = np.clip(audio.reshape(-1), -1.0, 1.0)
        pcm16 = (pcm * 32767.0).astype(np.int16)
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16_000)
            wav.writeframes(pcm16.tobytes())


class LocalTranscriber:
    """ASR router. Auto mode prefers configured whisper.cpp and otherwise uses faster-whisper."""

    def __init__(self, *, backend: str = "auto", model_name: str = "base", language: str = "", device: str = "cpu", compute_type: str = "int8", beam_size: int = 3, vad_filter: bool = True, whisper_cpp_executable: str = "", whisper_cpp_model: str = "", whisper_cpp_threads: int = 4) -> None:
        cpp_ready = bool(whisper_cpp_executable and whisper_cpp_model and Path(whisper_cpp_executable).expanduser().is_file() and Path(whisper_cpp_model).expanduser().is_file())
        if backend == "whisper_cpp" or (backend == "auto" and cpp_ready):
            self._impl = WhisperCppTranscriber(whisper_cpp_executable, whisper_cpp_model, language, whisper_cpp_threads)
        else:
            self._impl = FasterWhisperTranscriber(model_name, language, device, compute_type, beam_size, vad_filter)

    @property
    def engine_name(self) -> str:
        return self._impl.engine_name

    def preload(self) -> None:
        self._impl.preload()

    def update_options(self, language: str, beam_size: int, vad_filter: bool) -> None:
        self._impl.update_options(language, beam_size, vad_filter)

    def transcribe(self, audio: np.ndarray, hotwords: str | None = None) -> str:
        return self._impl.transcribe(audio, hotwords)
