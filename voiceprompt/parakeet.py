from __future__ import annotations

import hashlib
import os
import re
import shutil
import urllib.request
import uuid
from collections import deque
from pathlib import Path

import numpy as np

from voiceprompt.config import config_dir


MODEL_REPO = "csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
MODEL_REVISION = "1ab9323565ddb038682214b292f588070a538ce2"
MODEL_FILES = {
    "encoder.int8.onnx": 652184296,
    "decoder.int8.onnx": 7257753,
    "joiner.int8.onnx": 1739080,
    "tokens.txt": 9384,
}
VAD_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"
VAD_SHA256 = "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6"


def model_files() -> dict[str, Path]:
    """Reuse a pinned local cache; download weights only when missing/corrupt."""
    from huggingface_hub import hf_hub_download
    from huggingface_hub.utils import LocalEntryNotFoundError, disable_progress_bars

    disable_progress_bars()
    files = {}
    for name, expected_size in MODEL_FILES.items():
        try:
            path = Path(hf_hub_download(MODEL_REPO, name, revision=MODEL_REVISION, local_files_only=True))
        except LocalEntryNotFoundError:
            path = Path(hf_hub_download(MODEL_REPO, name, revision=MODEL_REVISION))
        if path.stat().st_size != expected_size:
            path = Path(hf_hub_download(MODEL_REPO, name, revision=MODEL_REVISION, force_download=True))
        if path.stat().st_size != expected_size:
            raise RuntimeError(f"Parakeet model file is incomplete: {name}")
        files[name] = path
    return files


def vad_file() -> Path:
    path = config_dir() / "models" / "silero_vad.onnx"
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == VAD_SHA256:
        return path
    if os.environ.get("HF_HUB_OFFLINE") == "1":
        raise RuntimeError("The Parakeet speech detector is not cached. Prepare it while online first.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"silero_vad-{uuid.uuid4().hex}.tmp")
    try:
        with urllib.request.urlopen(VAD_URL, timeout=30) as source, temporary.open("wb") as output:
            shutil.copyfileobj(source, output)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != VAD_SHA256:
            raise RuntimeError("The downloaded speech detector failed its checksum. No audio was captured.")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


class ParakeetTranscriber:
    """Decode completed phrases during speech, then finalize once on release."""

    backend_name = "parakeet"
    streaming = True  # Phrase processing, rather than a native streaming encoder.

    def __init__(self, cpu_threads: int = 4) -> None:
        self.cpu_threads = cpu_threads
        self.loaded_model = ""
        self.fallback_reason = ""
        self._recognizer = None
        self._vad = None
        self._texts: list[str] = []
        self._active = False
        self._warmed = False
        self._history: deque[tuple[int, np.ndarray]] = deque()
        self._samples_seen = 0
        self._last_decoded_end = 0

    def preload(self) -> None:
        if self._recognizer is None:
            import sherpa_onnx

            files = model_files()
            detector = str(vad_file())
            recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(files["encoder.int8.onnx"]), decoder=str(files["decoder.int8.onnx"]),
                joiner=str(files["joiner.int8.onnx"]), tokens=str(files["tokens.txt"]),
                num_threads=self.cpu_threads, provider="cpu", model_type="nemo_transducer",
            )
            config = sherpa_onnx.VadModelConfig()
            config.silero_vad.model = detector
            config.silero_vad.min_silence_duration = 0.3
            config.silero_vad.min_speech_duration = 0.1
            config.silero_vad.max_speech_duration = 10
            config.sample_rate = 16000
            config.num_threads = 1
            vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)
            self._recognizer = recognizer
            self._vad = vad
            self.loaded_model = "parakeet-tdt-0.6b-v2-int8"
        if not self._warmed:
            self._decode(np.zeros(16000, dtype=np.float32))
            self._warmed = True

    def begin_session(self, hotwords: str | None = None) -> None:
        # Greedy Parakeet decoding has no vocabulary boosting. Dictionary
        # replacements still run on final text in the application.
        self.preload()
        self.abort_session()
        self._active = True

    def accept_audio(self, audio: np.ndarray) -> None:
        if not self._active:
            raise RuntimeError("No active Parakeet session.")
        if len(audio):
            audio = np.asarray(audio, dtype=np.float32).reshape(-1)
            self._history.append((self._samples_seen, audio))
            self._samples_seen += len(audio)
            self._vad.accept_waveform(audio)
            self._drain()
            cutoff = max(0, self._samples_seen - 12 * 16000)
            while self._history and self._history[0][0] + len(self._history[0][1]) <= cutoff:
                self._history.popleft()
            if self._history and self._history[0][0] < cutoff:
                start, chunk = self._history.popleft()
                self._history.appendleft((cutoff, chunk[cutoff - start:].copy()))

    def _decode(self, audio: np.ndarray) -> str:
        stream = self._recognizer.create_stream()
        stream.accept_waveform(16000, audio)
        self._recognizer.decode_stream(stream)
        return stream.result.text.strip()

    def _drain(self) -> None:
        while not self._vad.empty():
            segment = self._vad.front
            # The detector can trigger after a quiet initial syllable. Recover
            # 250 ms of preceding audio, without repeating a decoded phrase.
            start = max(self._last_decoded_end, segment.start - 4000, 0)
            end = min(self._samples_seen, segment.start + len(segment.samples))
            pieces = [
                chunk[max(0, start - offset):min(len(chunk), end - offset)]
                for offset, chunk in self._history
                if offset < end and offset + len(chunk) > start
            ]
            text = self._decode(np.concatenate(pieces)) if pieces else ""
            self._last_decoded_end = end
            self._vad.pop()
            if text:
                self._texts.append(text)

    def finish_session(self) -> str:
        if not self._active:
            return ""
        try:
            # Complete any partial detector window, then preserve the final
            # phrase even when release happens before its silence endpoint.
            self._vad.accept_waveform(np.zeros(512, dtype=np.float32))
            self._vad.flush()
            self._drain()
            return re.sub(r"\s+", " ", " ".join(self._texts)).strip()
        finally:
            self.abort_session()

    def abort_session(self) -> None:
        self._active = False
        self._texts = []
        self._history.clear()
        self._samples_seen = 0
        self._last_decoded_end = 0
        if self._vad is not None:
            self._vad.reset()

    def close(self) -> None:
        self.abort_session()
        self._vad = None
        self._recognizer = None
        self._warmed = False
        self.loaded_model = ""
