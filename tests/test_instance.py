import ctypes
import os
import unittest
from ctypes import wintypes

from voiceprompt.instance import ShutdownRequest


@unittest.skipUnless(os.name == "nt", "Windows process shutdown event")
class ShutdownRequestTests(unittest.TestCase):
    def test_another_handle_can_request_shutdown_and_handles_are_closed(self):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.OpenEventW.restype = wintypes.HANDLE
        kernel32.SetEvent.argtypes = [wintypes.HANDLE]
        kernel32.SetEvent.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        with ShutdownRequest() as shutdown:
            self.assertFalse(shutdown.requested())
            remote_handle = kernel32.OpenEventW(0x0002, False, shutdown.name)
            self.assertTrue(remote_handle)
            try:
                self.assertTrue(kernel32.SetEvent(remote_handle))
                self.assertTrue(shutdown.requested())
            finally:
                kernel32.CloseHandle(remote_handle)
        self.assertFalse(shutdown.requested())
        self.assertFalse(kernel32.OpenEventW(0x0002, False, shutdown.name))

