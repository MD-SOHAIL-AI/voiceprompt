"""Exercise real delayed clipboard rendering in a private Windows station.

The interactive user's clipboard and keyboard are never used. If isolation
cannot be established, fail before any clipboard operation.
"""
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
import sys
import threading
import time
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    if sys.platform != 'win32': raise SystemExit('Windows is required.')
    user = c.WinDLL('user32', use_last_error=True)
    user.CreateWindowStationW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p]
    user.CreateWindowStationW.restype = w.HANDLE
    user.SetProcessWindowStation.argtypes = [w.HANDLE]
    user.GetProcessWindowStation.restype = w.HANDLE
    user.CreateDesktopW.argtypes = [w.LPCWSTR, w.LPCWSTR, c.c_void_p, w.DWORD, w.DWORD, c.c_void_p]
    user.CreateDesktopW.restype = w.HANDLE
    user.SetThreadDesktop.argtypes = [w.HANDLE]
    user.GetUserObjectInformationW.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)]
    name = 'VoicePrompt.ClipboardTest.' + uuid.uuid4().hex
    station = user.CreateWindowStationW(name, 0, 0x000F037F, None)
    if not station or not user.SetProcessWindowStation(station):
        raise RuntimeError('Private window-station isolation is unavailable. No clipboard was accessed.')
    desktop = user.CreateDesktopW('Default', None, None, 0, 0x000F01FF, None)
    if not desktop or not user.SetThreadDesktop(desktop):
        raise RuntimeError('Private desktop isolation is unavailable. No clipboard was accessed.')
    actual, size = c.create_unicode_buffer(256), w.DWORD()
    if not user.GetUserObjectInformationW(user.GetProcessWindowStation(), 2, actual, c.sizeof(actual), c.byref(size)) or actual.value != name:
        raise RuntimeError('Window-station isolation could not be verified. No clipboard was accessed.')
    import pyperclip
    import voiceprompt.clipboard as clipboard
    from voiceprompt.injector import TextInjector
    owner = clipboard._ClipboardOwner(desktop=desktop)
    clipboard._owner = owner
    api, kernel = clipboard._api()
    destination = api.CreateWindowExW(0, 'STATIC', 'Isolated paste destination', 0, 0, 0, 0, 0, None, None, None, None)
    assert destination
    received, failures, tasks = [], [], []
    def shortcut():
        def read():
            try:
                assert user.SetThreadDesktop(desktop)
                time.sleep(.4)  # Beyond the defective 250 ms restore deadline.
                assert api.OpenClipboard(destination)
                try:
                    handle = api.GetClipboardData(13)
                    pointer = kernel.GlobalLock(handle)
                    assert pointer
                    try: received.append(c.wstring_at(pointer))
                    finally: kernel.GlobalUnlock(handle)
                finally: api.CloseClipboard()
            except BaseException as exc: failures.append(repr(exc))
        task = threading.Thread(target=read)
        tasks.append(task); task.start()
    pyperclip.copy('original clipboard')
    injector = TextInjector()
    with patch('voiceprompt.injector.foreground_window', return_value=destination), patch('voiceprompt.injector.modifiers_down', return_value=False), patch('voiceprompt.injector.paste_shortcut', side_effect=shortcut):
        injector.inject('complete dictated sentence', target_window=destination)
    tasks[0].join(3)
    deadline = time.monotonic() + 2
    while injector.can_restore and time.monotonic() < deadline: time.sleep(.02)
    assert not failures, failures
    assert received == ['complete dictated sentence'], received
    assert pyperclip.paste() == 'original clipboard', 'The original clipboard was not restored after consumption.'
    api.DestroyWindow(destination)
    print(json.dumps({'passed': True, 'isolation': 'private window station', 'checks': ['real delayed rendering', '400ms destination read', 'consumption-aware restoration']}))


if __name__ == '__main__': main()
