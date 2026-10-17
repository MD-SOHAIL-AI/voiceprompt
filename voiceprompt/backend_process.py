"""A persistent, killable ASR worker. No model libraries are imported by the UI."""
from __future__ import annotations

import copy
import multiprocessing as mp
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from voiceprompt.config import config_dir


def run_worker(handle: int):
    from multiprocessing.connection import PipeConnection
    connection = PipeConnection(handle)
    backend = None
    try:
        settings = connection.recv()
        from voiceprompt.downloads import install_progress_reporting
        progress_lock = threading.Lock()
        def report(value):
            with progress_lock:
                connection.send(("progress", value))
        install_progress_reporting(report)
        if settings.backend == "nemotron":
            from voiceprompt.nemotron import NemotronTranscriber
            backend = NemotronTranscriber(settings.nemotron_device)
        else:
            from voiceprompt.transcriber import create_transcriber
            backend = create_transcriber(settings)
        while True:
            command, argument = connection.recv()
            try:
                if command == "close":
                    backend.close()
                    connection.send(("ok", None, "", ""))
                    return
                if command == "describe":
                    import importlib
                    if backend.backend_name == "parakeet":
                        importlib.import_module("sherpa_onnx")
                    elif backend.backend_name == "moonshine":
                        importlib.import_module("moonshine_voice.transcriber")
                    value = {"backend": backend.backend_name, "streaming": backend.streaming}
                elif command == "options":
                    backend.update_options(*argument)
                    value = None
                else:
                    method = getattr(backend, command)
                    value = method() if argument is None else method(argument)
                connection.send(("ok", value, backend.loaded_model, backend.fallback_reason))
            except Exception as exc:
                # Exceptions can contain private paths; report only type and a safe action.
                connection.send(("error", type(exc).__name__))
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        if backend is not None:
            backend.close()
        connection.close()


class ManagedTranscriber:
    def __init__(self, settings):
        self.settings = copy.deepcopy(settings)
        self.backend_name = settings.backend
        self.streaming = settings.backend != "whisper"
        self.loaded_model = ""
        self.fallback_reason = ""
        self.progress = None
        self._process = self._connection = None
        self._lock = threading.RLock()

    def _start(self):
        if self._process is not None and self._process.poll() is None:
            return
        self.interrupt()
        parent, child = mp.Pipe()
        try:
            os.set_handle_inheritable(child.fileno(), True)
            startup = subprocess.STARTUPINFO()
            startup.lpAttributeList = {"handle_list": [child.fileno()]}
            if getattr(sys, "frozen", False):
                command = [sys.executable, "--speech-worker", str(child.fileno())]
            else:
                # Windows' venv exe is a redirector that starts another process.
                # Monitor/kill the interpreter that actually owns native allocations.
                bootstrap = (f"import sys; sys.path = {sys.path!r}; "
                             f"from voiceprompt.backend_process import run_worker; run_worker({child.fileno()!r})")
                command = [getattr(sys, "_base_executable", sys.executable), "-c", bootstrap]
            self._process = subprocess.Popen(
                command, startupinfo=startup, close_fds=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                cwd=None if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent,
            )
            self._connection = parent
            parent.send(self.settings)
        except Exception:
            parent.close()
            self.interrupt()
            raise
        finally:
            os.set_handle_inheritable(child.fileno(), False)
            child.close()

    def _exchange(self, command, argument=None, timeout=30):
        with self._lock:
            connection = self._connection
            if connection is None:
                raise RuntimeError("The speech worker is unavailable. Prepare the model again.")
            try:
                connection.send((command, argument))
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if not connection.poll(min(0.05, max(0, deadline - time.monotonic()))):
                        continue
                    reply = connection.recv()
                    if reply[0] == "progress":
                        if self.progress:
                            self.progress(reply[1])
                        continue
                    if reply[0] == "error":
                        raise RuntimeError(f"Speech engine failed ({reply[1]}). Prepare the model or retry the recording.")
                    _, value, self.loaded_model, self.fallback_reason = reply
                    return value
                raise RuntimeError("The speech worker stopped responding. Prepare the model again.")
            except (EOFError, BrokenPipeError, OSError) as exc:
                self.interrupt()
                raise RuntimeError("The speech worker stopped. Free some memory, then prepare the model or retry.") from exc
            except Exception:
                self.interrupt()
                raise

    def preload(self):
        self._start()
        self._exchange("preload", timeout=1800)

    def begin_session(self, hotwords=None):
        self._exchange("begin_session", hotwords)

    def accept_audio(self, audio):
        if len(audio):
            self._exchange("accept_audio", audio, timeout=30)

    def finish_session(self):
        return self._exchange("finish_session")

    def abort_session(self):
        if self._connection is not None:
            self._exchange("abort_session", timeout=2)

    def update_options(self, language, beam_size, vad_filter):
        self.settings.language, self.settings.beam_size, self.settings.vad_filter = language, beam_size, vad_filter
        if self._connection is not None:
            self._exchange("options", (language, beam_size, vad_filter))

    def interrupt(self):
        # Deliberately does not acquire the RPC lock: cancellation must unblock recv.
        process, connection = self._process, self._connection
        self._process = self._connection = None
        self.loaded_model = ""
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if connection is not None:
            connection.close()

    def close(self):
        self.interrupt()


def create_managed_transcriber(settings):
    return ManagedTranscriber(settings)
