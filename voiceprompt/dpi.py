"""Set Windows DPI behavior before UI and input libraries choose a legacy default."""
from __future__ import annotations

import ctypes
import sys


def enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        aware = user32.SetProcessDpiAwarenessContext
        aware.argtypes = [ctypes.c_void_p]
        aware.restype = ctypes.c_bool
        aware(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2; respects an existing manifest.
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError):
                pass
