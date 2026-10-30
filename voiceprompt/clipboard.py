"""Bounded Win32 clipboard snapshots. Unsupported formats are left untouched."""
from __future__ import annotations

import ctypes as c
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass


def sequence_number():
    return c.windll.user32.GetClipboardSequenceNumber() if sys.platform == "win32" else 0


class ClipboardUnavailable(RuntimeError):
    pass


def _api():
    from ctypes import wintypes as w
    user, kernel = c.WinDLL("user32", use_last_error=True), c.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateWindowExW": ([w.DWORD,w.LPCWSTR,w.LPCWSTR,w.DWORD,c.c_int,c.c_int,c.c_int,c.c_int,w.HWND,w.HMENU,w.HINSTANCE,c.c_void_p], w.HWND),
        "DestroyWindow": ([w.HWND],w.BOOL), "OpenClipboard": ([w.HWND],w.BOOL),
        "CloseClipboard": ([],w.BOOL), "EmptyClipboard": ([],w.BOOL),
        "EnumClipboardFormats": ([w.UINT],w.UINT), "GetClipboardData": ([w.UINT],w.HANDLE),
        "SetClipboardData": ([w.UINT,w.HANDLE],w.HANDLE),
    }
    for name,(args,result) in signatures.items():
        function=getattr(user,name); function.argtypes=args; function.restype=result
    for name,args,result in (("GlobalSize",[w.HGLOBAL],c.c_size_t),("GlobalLock",[w.HGLOBAL],c.c_void_p),
                              ("GlobalUnlock",[w.HGLOBAL],w.BOOL),("GlobalAlloc",[w.UINT,c.c_size_t],w.HGLOBAL),
                              ("GlobalFree",[w.HGLOBAL],w.HGLOBAL)):
        function=getattr(kernel,name); function.argtypes=args; function.restype=result
    return user,kernel


@contextmanager
def _opened(user):
    window=user.CreateWindowExW(0,"STATIC","VoicePrompt clipboard",0,0,0,0,0,None,None,None,None)
    if not window: raise ClipboardUnavailable("Clipboard preservation is unavailable. Use Copy.")
    opened=False
    try:
        deadline=time.monotonic()+.2
        while not user.OpenClipboard(window):
            if time.monotonic() >= deadline: raise ClipboardUnavailable("The clipboard is busy. Use Copy.")
            time.sleep(.005)
        opened=True
        yield
    finally:
        if opened: user.CloseClipboard()
        user.DestroyWindow(window)


def _write(user,kernel,formats):
    allocated=[]
    try:
        for kind,data in formats:
            handle=kernel.GlobalAlloc(0x0002,len(data))
            if not handle: raise ClipboardUnavailable("Clipboard allocation failed. Use Copy.")
            allocated.append([kind,handle])
            pointer=kernel.GlobalLock(handle)
            if not pointer: raise ClipboardUnavailable("Clipboard allocation failed. Use Copy.")
            try: c.memmove(pointer,data,len(data))
            finally: kernel.GlobalUnlock(handle)
        if not user.EmptyClipboard(): raise ClipboardUnavailable("The clipboard is unavailable. Use Copy.")
        for item in allocated:
            if not user.SetClipboardData(item[0],item[1]): raise ClipboardUnavailable("The clipboard could not be updated. Use Copy.")
            item[1]=None  # Windows now owns this allocation.
    finally:
        for _,handle in allocated:
            if handle: kernel.GlobalFree(handle)


@dataclass
class ClipboardSnapshot:
    formats: list
    sequence: int

    def replace_text(self,text):
        user,kernel=_api()
        with _opened(user):
            if sequence_number() != self.sequence:
                raise ClipboardUnavailable("The clipboard changed. Your text is available to Copy.")
            try:
                _write(user,kernel,[(13,(text+'\0').encode('utf-16-le'))])
            except ClipboardUnavailable:
                _write(user,kernel,self.formats)
                raise
            return sequence_number()

    def restore(self,expected_sequence):
        user,kernel=_api()
        with _opened(user):
            if sequence_number() != expected_sequence: return
            _write(user,kernel,self.formats)


def snapshot_clipboard():
    if sys.platform != "win32": return None
    user,kernel=_api()
    formats,total=[],0
    with _opened(user):
        kind=0
        while True:
            c.set_last_error(0)
            kind=user.EnumClipboardFormats(kind)
            if not kind:
                if c.get_last_error(): raise ClipboardUnavailable("Clipboard formats could not be read. Use Copy.")
                break
            # Bitmap/metafile/owner-managed handles cannot be copied as HGLOBAL.
            if kind not in {1,4,5,7,8,10,11,12,13,15,16,17} and kind < 0xC000:
                raise ClipboardUnavailable("This clipboard format cannot be preserved. Your text is available to Copy.")
            handle=user.GetClipboardData(kind)
            size=kernel.GlobalSize(handle) if handle else 0
            total+=size
            if not size or total > 8*1024*1024 or len(formats) >= 256:
                raise ClipboardUnavailable("This clipboard cannot be safely preserved. Use Copy.")
            pointer=kernel.GlobalLock(handle)
            if not pointer: raise ClipboardUnavailable("Clipboard data could not be preserved. Use Copy.")
            try: formats.append((kind,c.string_at(pointer,size)))
            finally: kernel.GlobalUnlock(handle)
        return ClipboardSnapshot(formats,sequence_number())
