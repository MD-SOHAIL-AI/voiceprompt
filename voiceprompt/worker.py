from __future__ import annotations

import ctypes
import sys
import threading


class AudioWorkerContext:
    """Initialize WASAPI's COM context on the thread that owns capture."""

    def __init__(self) -> None:
        self._library = None
        self._owner: int | None = None

    def initialize(self) -> None:
        if sys.platform != "win32":
            return
        if self._library is not None:
            if self._owner != threading.get_ident():
                raise RuntimeError("The audio context belongs to another thread.")
            return
        library = ctypes.WinDLL("ole32")
        library.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        library.CoInitializeEx.restype = ctypes.c_long
        library.CoUninitialize.argtypes = []
        library.CoUninitialize.restype = None
        result = library.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED
        if result < 0:
            raise RuntimeError(f"Windows audio COM initialization failed: 0x{result & 0xffffffff:08x}")
        # Both S_OK and S_FALSE require a matching CoUninitialize.
        self._library = library
        self._owner = threading.get_ident()

    def close(self) -> None:
        if self._library is None:
            return
        if self._owner != threading.get_ident():
            raise RuntimeError("The audio context must close on its owning thread.")
        self._library.CoUninitialize()
        self._library = None
        self._owner = None
