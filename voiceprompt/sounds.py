from __future__ import annotations

import logging
import threading
from pathlib import Path

try:
    import winsound
except ImportError:  # Allows headless service tests on other operating systems.
    winsound = None


class SoundFeedback:
    """Short, asynchronous WAV cues. Audio failures never become dictation failures."""

    def __init__(self) -> None:
        self._closed = False
        self._lock = threading.Lock()
        self._directory = Path(__file__).resolve().parent / "assets"

    def play(self, cue: str) -> bool:
        if cue not in {"start", "stop", "reminder"}:
            return False
        with self._lock:
            if self._closed or winsound is None:
                return False
            try:
                winsound.PlaySound(
                    str(self._directory / f"{cue}.wav"),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
                return True
            except (RuntimeError, OSError):
                logging.getLogger(__name__).warning("Unable to play %s cue", cue)
                return False

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if winsound is not None:
                try:
                    winsound.PlaySound(None, 0)
                except (RuntimeError, OSError):
                    pass

    def stop(self) -> None:
        with self._lock:
            if not self._closed and winsound is not None:
                try:
                    winsound.PlaySound(None, 0)
                except (RuntimeError, OSError):
                    pass
