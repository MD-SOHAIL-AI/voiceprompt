"""Bounded local phrase decoding with exact, non-overlapping sample ownership."""
from __future__ import annotations
import numpy as np


class PhraseBuffer:
    def __init__(self, detector, *, sample_rate=16000, max_seconds=10):
        self.detector, self.rate = detector, sample_rate
        self.maximum = round(sample_rate * max_seconds)
        self.pending = np.empty(0, dtype=np.float32)
        self.next_check = sample_rate

    def push(self, audio, *, final=False):
        self.pending = np.concatenate((self.pending, audio))
        result = []
        while len(self.pending) >= self.maximum:
            cut = self._boundary(self.pending[:self.maximum]) or self.maximum
            result.append(self.pending[:cut])
            self.pending = self.pending[cut:]
            self.next_check = self.rate
        if len(self.pending) >= self.next_check:
            cut = self._boundary(self.pending)
            if cut:
                result.append(self.pending[:cut])
                self.pending = self.pending[cut:]
            self.next_check = len(self.pending) + self.rate // 2
        if final and len(self.pending):
            result.append(self.pending)
            self.pending = np.empty(0, dtype=np.float32)
        return result

    def _boundary(self, audio):
        segments = self.detector(audio)
        complete = [int(segment["end"]) for segment in segments if 0 < segment["end"] <= len(audio) - self.rate // 5]
        return max(complete, default=0)
