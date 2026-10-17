from __future__ import annotations

import ctypes
import importlib.util
import sys
from pathlib import Path

import numpy as np
import soxr


class RNNoise:
    """Use pyrnnoise's bundled native library without importing its DSP extras."""

    frame_size = 480

    def __init__(self) -> None:
        bundled = Path(getattr(sys, "_MEIPASS", "")) / "pyrnnoise"
        if getattr(sys, "frozen", False) and bundled.is_dir():
            root = bundled
        else:
            spec = importlib.util.find_spec("pyrnnoise")
            if spec is None or not spec.origin:
                raise RuntimeError("RNNoise is not installed. Install requirements-noise.txt.")
            root = Path(spec.origin).parent
        libraries = [p for p in root.rglob("*") if p.suffix in {".dll", ".so", ".dylib"} and "rnnoise" in p.name]
        if not libraries:
            raise RuntimeError("The RNNoise native library is missing. Reinstall requirements-noise.txt.")
        self._lib = ctypes.CDLL(str(libraries[0]))
        pointer = ctypes.POINTER(ctypes.c_float)
        self._lib.rnnoise_create.argtypes = [ctypes.c_void_p]
        self._lib.rnnoise_create.restype = ctypes.c_void_p
        self._lib.rnnoise_process_frame.argtypes = [ctypes.c_void_p, pointer, pointer]
        self._lib.rnnoise_process_frame.restype = ctypes.c_float
        self._lib.rnnoise_destroy.argtypes = [ctypes.c_void_p]
        self._lib.rnnoise_destroy.restype = None
        self._state = self._lib.rnnoise_create(None)
        if not self._state:
            raise RuntimeError("Could not allocate RNNoise state.")
        self._pending = np.empty(0, dtype=np.float32)
        self._skip = self.frame_size

    def process(self, audio: np.ndarray, final: bool = False) -> np.ndarray:
        self._pending = np.concatenate((self._pending, audio))
        if final:
            self._pending = np.pad(self._pending, (0, (-len(self._pending)) % self.frame_size + self.frame_size))
        output = []
        while len(self._pending) >= self.frame_size:
            frame = np.ascontiguousarray(self._pending[:self.frame_size] * 32768, dtype=np.float32)
            self._pending = self._pending[self.frame_size:]
            pointer = frame.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            self._lib.rnnoise_process_frame(self._state, pointer, pointer)
            if self._skip:
                self._skip = 0
            else:
                output.append(frame / 32768)
        return np.concatenate(output) if output else np.empty(0, dtype=np.float32)

    def close(self) -> None:
        if self._state:
            self._lib.rnnoise_destroy(self._state)
            self._state = None


class AudioProcessor:
    """Stateful resampling keeps filter history across variable capture blocks."""

    def __init__(self, sample_rate: int, noise_suppression: bool = False) -> None:
        self._denoiser = RNNoise() if noise_suppression else None
        intermediate_rate = 48000 if noise_suppression else 16000
        self._input = (
            soxr.ResampleStream(sample_rate, intermediate_rate, 1, dtype="float32", quality="HQ")
            if sample_rate != intermediate_rate else None
        )
        self._output = soxr.ResampleStream(48000, 16000, 1, dtype="float32", quality="HQ") if noise_suppression else None
        self._input_samples = 0
        self._output_samples = 0
        self._sample_rate = sample_rate

    def process(self, audio: np.ndarray, final: bool = False) -> np.ndarray:
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        self._input_samples += len(audio)
        if self._input is not None:
            audio = self._input.resample_chunk(audio, last=final)
        if self._denoiser is not None:
            audio = self._denoiser.process(audio, final=final)
        if self._output is not None:
            audio = self._output.resample_chunk(audio, last=final)
        if final:
            remaining = max(0, round(self._input_samples * 16000 / self._sample_rate) - self._output_samples)
            audio = audio[:remaining]
        self._output_samples += len(audio)
        return audio

    def close(self) -> None:
        if self._denoiser is not None:
            self._denoiser.close()
