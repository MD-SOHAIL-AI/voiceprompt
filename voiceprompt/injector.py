from __future__ import annotations

import threading
import time

import pyperclip
from pyperclip import PyperclipException

from voiceprompt.windows import paste_shortcut, foreground_window, modifiers_down
from voiceprompt.clipboard import snapshot_clipboard, sequence_number, ClipboardSnapshot, publish_delayed_text


class PasteError(RuntimeError):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


class TextInjector:
    """Serialize clipboard handoffs; a shortcut is not an insertion receipt."""

    def __init__(self, preserve_clipboard: bool = True, restore_delay: float = 0.25) -> None:
        self.preserve_clipboard = preserve_clipboard
        self.restore_delay = restore_delay  # Compatibility; not a paste deadline.
        self._lock = threading.RLock()
        self._generation = 0
        self._previous = None
        self._sequence = None
        self._text = ""
        self._lease = None

    def _owns(self):
        if self._lease is not None:
            return self._lease.owns()
        return self._sequence is not None and sequence_number() == self._sequence

    @property
    def can_restore(self):
        with self._lock:
            return self._previous is not None and self._owns()

    def inject(self, text: str, target_window: int = 0, cancelled=None, *, replace_clipboard=False) -> float:
        if not text.strip():
            return time.perf_counter()
        with self._lock:
            self._generation += 1
            generation = self._generation
            if cancelled and cancelled():
                raise PasteError("cancelled", "Paste cancelled.")
            if target_window and foreground_window() != target_window:
                raise PasteError("focus_changed", "The destination changed. Select Paste to previous app or Copy.")
            previous = self._previous if self._owns() else None
            if isinstance(previous, ClipboardSnapshot):
                previous = ClipboardSnapshot(previous.formats, sequence_number())
            if previous is None and self.preserve_clipboard and not replace_clipboard:
                try:
                    previous = snapshot_clipboard()
                    if previous is None:
                        previous = pyperclip.paste()
                except (RuntimeError, OSError, PyperclipException) as exc:
                    raise PasteError("clipboard_preservation", f"{exc} Select Paste and replace clipboard to insert your transcript without restoring the previous clipboard, or use Copy.") from exc
            if cancelled and cancelled():
                raise PasteError("cancelled", "Paste cancelled.")
            self._lease = None
            self._previous = previous
            try:
                if isinstance(previous, ClipboardSnapshot):
                    self._lease = publish_delayed_text(text, previous, target_window)
                    self._sequence = self._lease.sequence
                else:
                    pyperclip.copy(text)
                    self._sequence = sequence_number()
                self._text = text
                time.sleep(0.04)
                if cancelled and cancelled():
                    raise PasteError("cancelled", "Paste cancelled.")
                if target_window and foreground_window() != target_window:
                    raise PasteError("focus_changed", "The destination changed. Your transcript is ready to insert.")
                if not self._owns():
                    raise PasteError("clipboard_changed", "The clipboard changed before paste. Your transcript is still available.")
                if modifiers_down():
                    raise PasteError("modifier_held", "Release the recording key and other modifiers, then try Paste again.")
                if self._lease is not None:
                    self._lease.arm()
                paste_shortcut()
            except Exception:
                if previous is not None and self._owns() and (self._lease is not None or pyperclip.paste() == text):
                    try:
                        self._restore(previous, self._lease.sequence if self._lease else self._sequence)
                        self._previous = None
                    except (RuntimeError, OSError, PyperclipException):
                        pass
                raise
            sent_at = time.perf_counter()
            lease = self._lease
        if lease is not None and previous is not None:
            threading.Thread(target=self._restore_after_read, args=(lease, generation), name="clipboard-handoff", daemon=True).start()
        return sent_at

    def _restore_after_read(self, lease, generation):
        # An unattributable read (for example by a clipboard manager) must not
        # cause us to remove the transcript before the destination consumes it.
        if not lease.consumed.wait(5):
            return
        try:
            lease.wait_closed()
            with self._lock:
                if generation == self._generation and self._lease is lease:
                    self.restore_previous()
        except (RuntimeError, OSError):
            pass

    def restore_previous(self):
        with self._lock:
            if self._previous is None or not self._owns():
                self._previous = None
                return False
            sequence = self._lease.sequence if self._lease else self._sequence
            self._restore(self._previous, sequence)
            self._previous = None
            self._generation += 1
            return True

    @staticmethod
    def _restore(previous, sequence):
        if isinstance(previous, ClipboardSnapshot):
            previous.restore(sequence)
        else:
            pyperclip.copy(previous)

    def cancel_restore(self):
        with self._lock:
            self._generation += 1
            if self._lease is not None:
                self._lease.materialize()
            self._previous = None

    def _restore_later(self, previous, injected, generation, sequence=None):
        """Old callers cannot establish consumption; never restore on a timer."""
