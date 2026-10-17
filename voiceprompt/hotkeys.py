from __future__ import annotations

from collections.abc import Callable
import queue
import threading
import time

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
        self._events = queue.SimpleQueue()
        self._stop = threading.Event()
        self._dispatch = None
        self._changed_at = 0.0

    @property
    def pressed(self):
        return self._pressed

    def start(self) -> None:
        self._stop.clear()
        self._events = queue.SimpleQueue()
        self._pressed = False
        self._dispatch = threading.Thread(target=self._dispatch_events, name="hotkey-events", daemon=True)
        self._dispatch.start()
        self._listener = keyboard.Listener(on_press=self._handle_press, on_release=self._handle_release)
        self._listener.start()

    def stop(self) -> None:
        self._stop.set()
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._pressed = False
        if self._dispatch and self._dispatch is not threading.current_thread():
            self._dispatch.join(timeout=1)

    def _dispatch_events(self):
        from voiceprompt.windows import key_down
        while not self._stop.is_set():
            try:
                event = self._events.get(timeout=0.05)
            except queue.Empty:
                # Recover a lost release outside the hook, after key state has settled.
                if self._pressed and time.monotonic() - self._changed_at > 0.15 and not key_down(self.hotkey):
                    self._handle_release(self._target_key())
                continue
            try:
                (self.on_press if event == "press" else self.on_release)()
            except Exception:
                # A consumer failure must not terminate the system-wide hook.
                import logging
                logging.getLogger(__name__).exception("Hotkey action failed")

    def _target_key(self) -> keyboard.Key | None:
        return KEYS.get(self.hotkey)

    def _handle_press(self, key: keyboard.Key | keyboard.KeyCode | None, injected=False) -> None:
        if injected or key != self._target_key() or self._pressed:
            return
        self._pressed = True
        self._changed_at = time.monotonic()
        self._events.put("press")

    def _handle_release(self, key: keyboard.Key | keyboard.KeyCode | None, injected=False) -> None:
        if injected or key != self._target_key() or not self._pressed:
            return
        self._pressed = False
        self._changed_at = time.monotonic()
        self._events.put("release")
