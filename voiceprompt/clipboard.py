"""Bounded Win32 clipboard snapshots. Unsupported formats are left untouched."""
from __future__ import annotations

import ctypes as c
import sys
import time
import threading
import queue
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


class DelayedText:
    def __init__(self, owner, text, target):
        self.owner, self.text, self.target = owner, text, target
        self.sequence = 0
        self.consumed = threading.Event()
        self.rendered = False

    def owns(self):
        return self.owner.current is self and self.owner.user.GetClipboardOwner() == self.owner.window and sequence_number() == self.sequence

    def materialize(self):
        if self.owns() and not self.rendered:
            self.owner.call(lambda: self.owner.materialize(self))

    def wait_closed(self):
        deadline = time.monotonic() + 1
        while self.owner.user.GetOpenClipboardWindow():
            if time.monotonic() >= deadline:
                raise ClipboardUnavailable("The destination still has the clipboard open.")
            time.sleep(.01)


class _ClipboardOwner:
    """A message-pumping owner survives the caller and delayed clipboard reads."""
    def __init__(self, *, desktop=None):
        self.desktop = desktop
        self.tasks = queue.Queue()
        self.ready = threading.Event()
        self.current = None
        self.error = None
        threading.Thread(target=self.run, name="clipboard-owner", daemon=True).start()
        if not self.ready.wait(3) or self.error:
            raise ClipboardUnavailable("Clipboard handoff could not start. Use Copy.")

    def call(self, callback):
        done, result = threading.Event(), []
        self.tasks.put((callback, done, result))
        self.user.PostMessageW(self.window, 0x8001, 0, 0)
        if not done.wait(3):
            raise ClipboardUnavailable("Clipboard handoff timed out. Use Copy.")
        if isinstance(result[0], BaseException):
            raise result[0]
        return result[0]

    def render(self, lease):
        data = (lease.text + '\0').encode('utf-16-le')
        handle = self.kernel.GlobalAlloc(0x0002, len(data))
        if not handle:
            raise ClipboardUnavailable("Clipboard allocation failed.")
        pointer = self.kernel.GlobalLock(handle)
        if not pointer:
            self.kernel.GlobalFree(handle)
            raise ClipboardUnavailable("Clipboard allocation failed.")
        try:
            c.memmove(pointer, data, len(data))
        finally:
            self.kernel.GlobalUnlock(handle)
        if not self.user.SetClipboardData(13, handle):
            self.kernel.GlobalFree(handle)
            raise ClipboardUnavailable("Clipboard rendering failed.")
        lease.rendered = True
        lease.sequence = sequence_number()

    def materialize(self, lease):
        if not lease.owns() or lease.rendered:
            return
        if not self.user.OpenClipboard(self.window):
            raise ClipboardUnavailable("The clipboard is busy.")
        try:
            self.render(lease)
        finally:
            self.user.CloseClipboard()

    def publish(self, text, previous, target):
        def publish():
            if not self.user.OpenClipboard(self.window):
                raise ClipboardUnavailable("The clipboard is busy. Try Paste again.")
            try:
                if sequence_number() != previous.sequence:
                    raise ClipboardUnavailable("The clipboard changed. Try Paste again.")
                if not self.user.EmptyClipboard():
                    raise ClipboardUnavailable("The clipboard could not be updated.")
                c.set_last_error(0)
                self.user.SetClipboardData(13, None)
                if c.get_last_error():
                    _write(self.user, self.kernel, previous.formats)
                    raise ClipboardUnavailable("Delayed clipboard rendering is unavailable.")
                lease = DelayedText(self, text, target)
                lease.sequence = sequence_number()
                self.current = lease
                return lease
            finally:
                self.user.CloseClipboard()
        return self.call(publish)

    def run(self):
        from ctypes import wintypes as w
        try:
            if self.desktop is not None:
                user = c.WinDLL('user32', use_last_error=True)
                user.SetThreadDesktop.argtypes = [w.HANDLE]
                if not user.SetThreadDesktop(self.desktop):
                    raise ClipboardUnavailable('Cannot enter the isolated clipboard test desktop.')
            self.user, self.kernel = _api()
            for name in ('GetClipboardOwner', 'GetOpenClipboardWindow'):
                getattr(self.user, name).restype = w.HWND
            self.user.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
            self.user.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
            proc_type = c.WINFUNCTYPE(c.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
            class WindowClass(c.Structure):
                _fields_ = [('style', w.UINT), ('proc', proc_type), ('cls', c.c_int), ('win', c.c_int),
                            ('instance', w.HINSTANCE), ('icon', w.HICON), ('cursor', w.HANDLE),
                            ('background', w.HBRUSH), ('menu', w.LPCWSTR), ('name', w.LPCWSTR)]
            self.user.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
            self.user.DefWindowProcW.restype = c.c_ssize_t
            def callback(hwnd, message, wp, lp):
                try:
                    if message == 0x8001:
                        while True:
                            try:
                                task, done, result = self.tasks.get_nowait()
                            except queue.Empty:
                                break
                            try:
                                result.append(task())
                            except BaseException as exc:
                                result.append(exc)
                            finally:
                                done.set()
                        return 0
                    lease = self.current
                    if message == 0x0305 and wp == 13 and lease is not None:
                        reader = self.user.GetOpenClipboardWindow()
                        reader_pid, target_pid = w.DWORD(), w.DWORD()
                        self.user.GetWindowThreadProcessId(reader, c.byref(reader_pid))
                        self.user.GetWindowThreadProcessId(lease.target, c.byref(target_pid))
                        self.render(lease)  # The reader already has it open.
                        if reader_pid.value and reader_pid.value == target_pid.value:
                            lease.consumed.set()
                        return 0
                    if message == 0x0306 and lease is not None:
                        self.materialize(lease)
                        return 0
                except Exception:
                    # Exceptions must never cross a native window callback.
                    return 0
                return self.user.DefWindowProcW(hwnd, message, wp, lp)
            self.callback = proc_type(callback)
            name = 'VoicePrompt.ClipboardOwner.' + str(id(self))
            wc = WindowClass(0, self.callback, 0, 0, None, None, None, None, None, name)
            self.user.RegisterClassW.argtypes = [c.POINTER(WindowClass)]
            if not self.user.RegisterClassW(c.byref(wc)):
                raise ClipboardUnavailable("Clipboard owner registration failed.")
            self.window = self.user.CreateWindowExW(0, name, 'VoicePrompt clipboard', 0, 0, 0, 0, 0, None, None, None, None)
            if not self.window:
                raise ClipboardUnavailable("Clipboard owner creation failed.")
            self.ready.set()
            message = w.MSG()
            self.user.GetMessageW.argtypes = [c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
            self.user.DispatchMessageW.argtypes = [c.POINTER(w.MSG)]
            self.user.DispatchMessageW.restype = c.c_ssize_t
            while self.user.GetMessageW(c.byref(message), None, 0, 0) > 0:
                self.user.DispatchMessageW(c.byref(message))
        except Exception as exc:
            self.error = exc
            self.ready.set()


_owner = None
_owner_lock = threading.Lock()


def publish_delayed_text(text, previous, target):
    global _owner
    with _owner_lock:
        if _owner is None:
            _owner = _ClipboardOwner()
    return _owner.publish(text, previous, target)
