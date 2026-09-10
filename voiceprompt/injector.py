from __future__ import annotations

import threading
import time

import pyautogui
import pyperclip


class TextInjector:
    def __init__(self, preserve_clipboard: bool = True, restore_delay: float = 0.25) -> None:
        self.preserve_clipboard = preserve_clipboard
        self.restore_delay = restore_delay

    def inject(self, text: str) -> None:
        if not text.strip():
            return

        previous: str | None = None
        if self.preserve_clipboard:
            try:
                previous = pyperclip.paste()
            except pyperclip.PyperclipException:
                previous = None

        pyperclip.copy(text)
        time.sleep(0.04)
        pyautogui.hotkey("ctrl", "v")

        if self.preserve_clipboard and previous is not None:
            threading.Thread(target=self._restore_later, args=(previous,), daemon=True).start()

    def _restore_later(self, previous: str) -> None:
        time.sleep(self.restore_delay)
        try:
            pyperclip.copy(previous)
        except pyperclip.PyperclipException:
            pass
