from __future__ import annotations

import threading
from collections.abc import Iterable

try:
    import winsound
except ImportError:  # pragma: no cover - Voice Prompt targets Windows
    winsound = None  # type: ignore[assignment]


TonePattern = tuple[tuple[int, int], ...]

# Short, intentionally distinct cues. The active cue rises; the inactive cue falls.
ACTIVE_PATTERN: TonePattern = ((880, 40), (1175, 55))
INACTIVE_PATTERN: TonePattern = ((1175, 40), (740, 60))


class SoundFeedback:
    """Plays tiny Windows tone cues for push-to-talk state changes.

    The active cue is synchronous so it finishes before the microphone starts,
    preventing the notification from being recorded. The inactive cue is safe to
    play asynchronously because recording has already stopped.
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._lock = threading.Lock()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def play_active(self) -> None:
        if not self.enabled:
            return
        self._play(ACTIVE_PATTERN)

    def play_inactive(self, asynchronous: bool = True) -> None:
        if not self.enabled:
            return
        if asynchronous:
            threading.Thread(target=self._play, args=(INACTIVE_PATTERN,), daemon=True).start()
        else:
            self._play(INACTIVE_PATTERN)

    def _play(self, pattern: Iterable[tuple[int, int]]) -> None:
        if winsound is None:
            return
        with self._lock:
            for frequency, duration_ms in pattern:
                try:
                    winsound.Beep(int(frequency), int(duration_ms))
                except (RuntimeError, OSError):
                    # Sound feedback must never break dictation if the audio device
                    # or Windows beep service is unavailable.
                    return
