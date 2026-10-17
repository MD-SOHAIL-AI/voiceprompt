"""Small Windows adapters; no UI toolkit or model imports."""
import ctypes
import sys


def foreground_window():
    if sys.platform != "win32":
        return 0
    library = ctypes.windll.user32
    library.GetForegroundWindow.restype = ctypes.c_void_p
    return library.GetForegroundWindow() or 0


def modifiers_down():
    if sys.platform != "win32":
        return False
    return any(ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000 for key in (0x10, 0x11, 0x12, 0x5B, 0x5C))


def key_down(hotkey):
    keys = {"right_ctrl": 0xA3, "left_ctrl": 0xA2, "right_alt": 0xA5, "left_alt": 0xA4, "f8": 0x77, "f9": 0x78}
    return bool(ctypes.windll.user32.GetAsyncKeyState(keys[hotkey]) & 0x8000) if sys.platform == "win32" else False


def paste_shortcut():
    """Inject Ctrl+V with the pointer-sized Win32 INPUT layout."""
    from ctypes import wintypes
    class KeyboardInput(ctypes.Structure):
        _fields_ = [("vk", wintypes.WORD), ("scan", wintypes.WORD), ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]
    class MouseInput(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG), ("data", wintypes.DWORD),
                    ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]
    class InputUnion(ctypes.Union):
        _fields_ = [("keyboard", KeyboardInput), ("mouse", MouseInput)]
    class Input(ctypes.Structure):
        _anonymous_ = ("payload",)
        _fields_ = [("type", wintypes.DWORD), ("payload", InputUnion)]
    inputs = (Input * 4)(*[Input(1, InputUnion(keyboard=KeyboardInput(key, 0, flags, 0, 0)))
                          for key, flags in ((0xA2, 0), (0x56, 0), (0x56, 2), (0xA2, 2))])
    library = ctypes.WinDLL("user32", use_last_error=True)
    library.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    library.SendInput.restype = wintypes.UINT
    if library.SendInput(4, inputs, ctypes.sizeof(Input)) != 4:
        raise RuntimeError("Windows could not paste into this application. Your text is available to Copy in VoicePrompt.")
