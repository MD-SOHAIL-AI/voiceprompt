"""Exercise real delayed clipboard rendering in a private Windows station.

The interactive user's clipboard and keyboard are never used locally. An
explicit CI option permits the disposable GitHub-hosted runner's clipboard
when a private station cannot be created. The keyboard is never injected.
"""
import ctypes as c
from ctypes import wintypes as w
import json
import argparse
import os
import struct
from pathlib import Path
import sys
import threading
import time
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-hosted-runner-clipboard', action='store_true')
    options = parser.parse_args()
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
    if not station:
        hosted = os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
        if not options.allow_hosted_runner_clipboard or not hosted:
            raise RuntimeError('Private window-station isolation is unavailable. No clipboard was accessed.')
        user.GetThreadDesktop.argtypes = [w.DWORD]
        user.GetThreadDesktop.restype = w.HANDLE
        desktop = user.GetThreadDesktop(c.windll.kernel32.GetCurrentThreadId())
        if not desktop:
            raise RuntimeError('The disposable runner desktop is unavailable.')
        isolation = 'disposable GitHub-hosted runner'
    else:
        if not user.SetProcessWindowStation(station):
            raise RuntimeError('Private station could not be selected. No clipboard was accessed.')
        desktop = user.CreateDesktopW('Default', None, None, 0, 0x000F01FF, None)
        if not desktop or not user.SetThreadDesktop(desktop):
            raise RuntimeError('Private desktop isolation is unavailable. No clipboard was accessed.')
        actual, size = c.create_unicode_buffer(256), w.DWORD()
        if not user.GetUserObjectInformationW(user.GetProcessWindowStation(), 2, actual, c.sizeof(actual), c.byref(size)) or actual.value != name:
            raise RuntimeError('Window-station isolation could not be verified. No clipboard was accessed.')
        isolation = 'private window station'
    import pyperclip
    import voiceprompt.clipboard as clipboard
    from voiceprompt.injector import TextInjector
    owner = clipboard._ClipboardOwner(desktop=desktop)
    clipboard._owner = owner
    api, kernel = clipboard._api()
    destination = api.CreateWindowExW(0, 'STATIC', 'Isolated paste destination', 0, 0, 0, 0, 0, None, None, None, None)
    assert destination
    def read_bytes(kind):
        deadline = time.monotonic() + 1
        while not api.OpenClipboard(destination):
            if time.monotonic() >= deadline: raise RuntimeError('Test reader could not open clipboard')
            time.sleep(.005)
        try:
            handle = api.GetClipboardData(kind)
            pointer = kernel.GlobalLock(handle)
            assert pointer, f'Clipboard format {kind} was not rendered'
            try: return c.string_at(pointer, kernel.GlobalSize(handle))
            finally: kernel.GlobalUnlock(handle)
        finally: api.CloseClipboard()

    def deliver(transcript, *, monitor_first=False):
        received, failures, tasks = [], [], []
        def shortcut():
            def read():
                try:
                    assert user.SetThreadDesktop(desktop)
                    time.sleep(.4)
                    received.append(read_bytes(13).decode('utf-16-le').split('\0')[0])
                except BaseException as exc: failures.append(repr(exc))
            task = threading.Thread(target=read)
            tasks.append(task); task.start()
        def publish(text, previous, target):
            lease = clipboard.publish_delayed_text(text, previous, target)
            if monitor_first:
                read_bytes(13)
                assert lease.consumed.is_set(), 'Pre-shortcut read was not reproduced'
            return lease
        injector = TextInjector()
        with patch('voiceprompt.injector.foreground_window', return_value=destination), patch('voiceprompt.injector.modifiers_down', return_value=False), patch('voiceprompt.injector.publish_delayed_text', side_effect=publish), patch('voiceprompt.injector.paste_shortcut', side_effect=shortcut):
            injector.inject(transcript, target_window=destination)
        tasks[0].join(3)
        assert not failures, failures
        assert received == [transcript], received
        if monitor_first:
            assert pyperclip.paste() == transcript, 'A monitor caused early clipboard restoration'
            assert injector.restore_previous()
        else:
            deadline = time.monotonic() + 2
            while injector.can_restore and time.monotonic() < deadline: time.sleep(.02)
        return injector

    pyperclip.copy('original clipboard')
    deliver('complete dictated sentence')
    assert pyperclip.paste() == 'original clipboard'
    pyperclip.copy('clipboard before monitor')
    deliver('complete sentence after monitor read', monitor_first=True)
    assert pyperclip.paste() == 'clipboard before monitor'

    # A real nine-megabyte image also exposes synthesized GDI/bitmap formats.
    width = height = 1536
    pixels = bytes((10, 20, 30, 255)) * (width * height)
    dib = struct.pack('<IiiHHIIiiII', 40, width, height, 1, 32, 0, len(pixels), 0, 0, 0, 0) + pixels
    with clipboard._opened(api): clipboard._write(api, kernel, [(8, dib)])
    deliver('text pasted over a screenshot clipboard')
    restored = read_bytes(8)
    assert struct.unpack_from('<ii', restored, 4) == (width, height), 'Screenshot dimensions changed'
    assert restored[-4:-1] == bytes((10, 20, 30)), 'Screenshot pixels were not restored'
    api.DestroyWindow(destination)
    report = {'passed': True, 'isolation': isolation, 'checks': ['real delayed rendering', '400ms destination read', 'consumption-aware restoration', 'monitor read before paste', 'nine-MB screenshot preservation']}
    report_path = Path(__file__).resolve().parents[1] / 'build/clipboard-handoff.json'
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__': main()
