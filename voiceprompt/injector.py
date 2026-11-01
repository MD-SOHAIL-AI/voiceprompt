from __future__ import annotations

import threading
import time

import pyperclip
from voiceprompt.windows import paste_shortcut, foreground_window
from voiceprompt.clipboard import snapshot_clipboard, sequence_number, ClipboardSnapshot


class TextInjector:
    def __init__(self, preserve_clipboard: bool = True, restore_delay: float = 0.25) -> None:
        self.preserve_clipboard = preserve_clipboard
        self.restore_delay = restore_delay
        self._lock = threading.Lock()
        self._generation = 0

    def inject(self, text: str, target_window: int = 0, cancelled=None) -> float:
        if not text.strip():
            return time.perf_counter()

        previous: str | None = None
        with self._lock:
            # Snapshot and replacement must be one transaction: overlapping
            # injections otherwise save another dictation as the user's clipboard.
            self._generation += 1
            generation = self._generation
            if cancelled and cancelled(): raise RuntimeError("Paste cancelled.")
            if target_window and foreground_window() != target_window:
                raise RuntimeError("The destination changed. Your text is available to Copy.")
            if self.preserve_clipboard:
                previous = snapshot_clipboard()
                if previous is None:
                    previous = pyperclip.paste()
            if cancelled and cancelled(): raise RuntimeError("Paste cancelled.")

            if isinstance(previous, ClipboardSnapshot):
                sequence = previous.replace_text(text)
            else:
                pyperclip.copy(text)
                sequence = sequence_number()
            try:
                time.sleep(0.04)
                if cancelled and cancelled(): raise RuntimeError("Paste cancelled.")
                if target_window and foreground_window() != target_window:
                    raise RuntimeError("The destination changed. Your text is available to Copy.")
                paste_shortcut()
            except Exception:
                # Ctrl+V can fail (e.g. an elevated target window). Do not
                # leave the dictated text in the clipboard after a failed paste.
                if previous is not None:
                    try:
                        if sequence_number() == sequence and pyperclip.paste() == text:
                            self._restore(previous, sequence)
                    except (pyperclip.PyperclipException, RuntimeError, OSError):
                        pass
                raise
            pasted_at = time.perf_counter()

        if self.preserve_clipboard and previous is not None:
            threading.Thread(target=self._restore_later, args=(previous, text, generation, sequence), daemon=True).start()
        return pasted_at

    def _restore_later(self, previous, injected: str, generation: int, sequence=None) -> None:
        time.sleep(self.restore_delay)
        try:
            with self._lock:
                if self._generation == generation and (sequence is None or sequence_number() == sequence) and pyperclip.paste() == injected:
                    self._restore(previous, sequence)
        except (pyperclip.PyperclipException, RuntimeError, OSError):
            pass

    @staticmethod
    def _restore(previous, sequence):
        if isinstance(previous, ClipboardSnapshot): previous.restore(sequence)
        else: pyperclip.copy(previous)

    def cancel_restore(self) -> None:
        with self._lock:
            self._generation += 1
