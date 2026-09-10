from __future__ import annotations

from collections.abc import Callable

from pynput import keyboard


KEYS = {
    "right_ctrl": keyboard.Key.ctrl_r,
    "left_ctrl": keyboard.Key.ctrl_l,
    "right_alt": keyboard.Key.alt_r,
    "left_alt": keyboard.Key.alt_l,
    "f8": keyboard.Key.f8,
    "f9": keyboard.Key.f9,
}


class PushToTalkHotkey:
    def __init__(self, hotkey: str, on_press: Callable[[], None], on_release: Callable[[], None]) -> None:
        self.hotkey = hotkey
        self.on_press = on_press
        self.on_release = on_release
        self._pressed = False
        self._listener: keyboard.Listener | None = None

    def start(self) -> None:
        self._listener = keyboard.Listener(on_press=self._handle_press, on_release=self._handle_release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _target_key(self) -> keyboard.Key | None:
        return KEYS.get(self.hotkey)

    def _handle_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key != self._target_key() or self._pressed:
            return
        self._pressed = True
        self.on_press()

    def _handle_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key != self._target_key() or not self._pressed:
            return
        self._pressed = False
        self.on_release()
