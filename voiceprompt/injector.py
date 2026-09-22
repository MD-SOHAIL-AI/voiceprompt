from __future__ import annotations

import ctypes
import os
import threading
import time

import pyautogui
import pyperclip


def capture_foreground_window() -> int | None:
    if os.name != "nt":
        return None
    hwnd = int(ctypes.windll.user32.GetForegroundWindow())
    return hwnd or None


def _focus_window(hwnd: int) -> bool:
    if os.name != "nt":
        return True
    user32 = ctypes.windll.user32
    if int(user32.GetForegroundWindow()) == hwnd:
        return True
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.05)
    return int(user32.GetForegroundWindow()) == hwnd


class TextInjector:
    def __init__(
        self,
        preserve_clipboard: bool = True,
        restore_delay: float = 0.25,
        restore_focus_on_paste: bool = True,
    ) -> None:
        self.preserve_clipboard = preserve_clipboard
        self.restore_delay = restore_delay
        self.restore_focus_on_paste = restore_focus_on_paste
        self._inject_lock = threading.Lock()

    def inject(self, text: str, target_window: int | None = None) -> bool:
        if not text.strip():
            return False

        with self._inject_lock:
            if target_window is not None:
                current = capture_foreground_window()
                if current != target_window:
                    if not self.restore_focus_on_paste or not _focus_window(target_window):
                        return False

            previous: str | None = None
            if self.preserve_clipboard:
                try:
                    previous = pyperclip.paste()
                except pyperclip.PyperclipException:
                    previous = None

            pyperclip.copy(text)
            time.sleep(0.025)
            pyautogui.hotkey("ctrl", "v")

            if self.preserve_clipboard and previous is not None:
                threading.Thread(
                    target=self._restore_later,
                    args=(previous, text),
                    daemon=True,
                ).start()
            return True

    def _restore_later(self, previous: str, injected_text: str) -> None:
        time.sleep(self.restore_delay)
        try:
            if pyperclip.paste() == injected_text:
                pyperclip.copy(previous)
        except pyperclip.PyperclipException:
            pass
