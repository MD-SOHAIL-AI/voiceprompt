from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    """Keeps one VoicePrompt process active per Windows login session."""

    def __init__(self, name: str = "Local\\VoicePrompt.SingleInstance") -> None:
        self._handle: int | None = None
        self.already_running = False
        if os.name != "nt":
            return

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.SetLastError(0)
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            raise ctypes.WinError()
        self._handle = handle
        self.already_running = kernel32.GetLastError() == ERROR_ALREADY_EXISTS

    def close(self) -> None:
        if self._handle is not None:
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> "SingleInstance":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
