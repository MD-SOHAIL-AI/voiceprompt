from __future__ import annotations

import threading
import time

import pyperclip
from voiceprompt.windows import paste_shortcut


class TextInjector:
    def __init__(self, preserve_clipboard: bool = True, restore_delay: float = 0.25) -> None:
        self.preserve_clipboard = preserve_clipboard
        self.restore_delay = restore_delay
        self._lock = threading.Lock()
        self._generation = 0

    def inject(self, text: str) -> float:
        if not text.strip():
            return time.perf_counter()

        previous: str | None = None
        with self._lock:
            # Snapshot and replacement must be one transaction: overlapping
            # injections otherwise save another dictation as the user's clipboard.
            self._generation += 1
            generation = self._generation
            if self.preserve_clipboard:
                try:
                    previous = pyperclip.paste()
                except pyperclip.PyperclipException:
                    previous = None

            pyperclip.copy(text)
            time.sleep(0.04)
            paste_shortcut()
            pasted_at = time.perf_counter()

        if self.preserve_clipboard and previous is not None:
            threading.Thread(target=self._restore_later, args=(previous, text, generation), daemon=True).start()
        return pasted_at

    def _restore_later(self, previous: str, injected: str, generation: int) -> None:
        time.sleep(self.restore_delay)
        try:
            with self._lock:
                if self._generation == generation and pyperclip.paste() == injected:
                    pyperclip.copy(previous)
        except pyperclip.PyperclipException:
            pass

    def cancel_restore(self) -> None:
        with self._lock:
            self._generation += 1
