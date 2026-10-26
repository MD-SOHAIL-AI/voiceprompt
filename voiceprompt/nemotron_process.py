"""Keep native assertions and graphics-driver failures outside the UI process."""
from __future__ import annotations

import multiprocessing as mp
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

from voiceprompt.nemotron import FEED_SAMPLES
from voiceprompt.config import config_dir


def _native_worker(connection, device: str) -> None:
    from voiceprompt.nemotron import NemotronTranscriber

    backend = NemotronTranscriber(device)
    try:
        while True:
            command, argument = connection.recv()
            try:
                if command == "preload":
                    value = backend.preload()
                elif command == "begin":
                    value = backend.begin_session(argument)
                elif command == "audio":
                    value = backend.accept_audio(argument)
                elif command == "finish":
                    value = backend.finish_session()
                elif command == "abort":
                    value = backend.abort_session()
                elif command == "close":
                    backend.close()
                    connection.send((True, None, ""))
                    return
                else:
                    raise ValueError("Unknown Nemotron worker command.")
                connection.send((True, value, backend.loaded_model))
            except Exception as exc:
                connection.send((False, f"{type(exc).__name__}: {exc}", ""))
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        backend.close()
        connection.close()


def run_worker(handle: int, device: str) -> None:
    from multiprocessing.connection import PipeConnection

    _native_worker(PipeConnection(handle), device)


def _worker_command(handle: int, device: str) -> list[str]:
    arguments = ["--nemotron-worker", str(handle), device]
    if getattr(sys, "frozen", False):
        return [sys.executable, *arguments]
    # The Windows venv executable is a redirector with its own child process.
    # Launch the real interpreter with this environment's module paths so the
    # process we monitor/terminate is the one owning the graphics allocations.
    bootstrap = f"import sys; sys.path = {sys.path!r}; from voiceprompt.nemotron_process import run_worker; run_worker({handle!r}, {device!r})"
    return [getattr(sys, "_base_executable", sys.executable), "-c", bootstrap]


class NemotronProcessTranscriber:
    """One persistent native worker; only local 100 ms audio blocks cross the pipe."""

    backend_name = "nemotron"
    streaming = True

    def __init__(self, device: str = "vulkan") -> None:
        if device not in {"vulkan", "cpu"}:
            raise ValueError("Nemotron processing must be vulkan or cpu.")
        self.device = device
        self.loaded_model = ""
        self.fallback_reason = ""
        self._process = None
        self._connection = None
        self._active = False
        self._pending = np.empty(0, dtype=np.float32)

    @property
    def worker_pid(self) -> int | None:
        return self._process.pid if self._process is not None else None

    def _start_worker(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        self._stop_worker()
        # Inherit exactly one Windows pipe. multiprocessing's normal spawn
        # imports the full GUI/evaluator again, wasting RAM on this laptop.
        parent, child = mp.Pipe()
        self._connection = parent
        try:
            os.set_handle_inheritable(child.fileno(), True)
            startup = subprocess.STARTUPINFO()
            startup.lpAttributeList = {"handle_list": [child.fileno()]}
            with (config_dir() / "nemotron-native.log").open("wb") as log:
                self._process = subprocess.Popen(
                    _worker_command(child.fileno(), self.device),
                    startupinfo=startup, close_fds=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    cwd=None if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent,
                )
        except Exception:
            parent.close()
            self._connection, self._process = None, None
            raise
        finally:
            os.set_handle_inheritable(child.fileno(), False)
            child.close()

    def _exchange(self, command, argument=None, timeout: float = 30):
        try:
            self._connection.send((command, argument))
            if not self._connection.poll(timeout):
                raise RuntimeError("Nemotron stopped responding. Nothing was pasted.")
            success, value, model = self._connection.recv()
            if not success:
                raise RuntimeError(value)
            self.loaded_model = model
            return value
        except (EOFError, BrokenPipeError, OSError) as exc:
            self._stop_worker()
            raise RuntimeError("Nemotron's native worker stopped. Free some memory or check the graphics driver, then warm the model again. Nothing was pasted.") from exc
        except Exception:
            self._stop_worker()
            raise

    def preload(self) -> None:
        self._start_worker()
        if not self.loaded_model:
            # First installation can download the pinned weights/runtime.
            self._exchange("preload", timeout=1800)

    def begin_session(self, hotwords: str | None = None) -> None:
        self.preload()
        self.abort_session()
        self._exchange("begin", hotwords)
        self._active = True

    def accept_audio(self, audio: np.ndarray) -> None:
        if not self._active:
            raise RuntimeError("No active Nemotron session.")
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if len(audio):
            self._pending = np.concatenate((self._pending, audio))
            while len(self._pending) >= FEED_SAMPLES:
                self._exchange("audio", np.ascontiguousarray(self._pending[:FEED_SAMPLES]), timeout=10)
                self._pending = self._pending[FEED_SAMPLES:]

    def finish_session(self) -> str:
        if not self._active:
            return ""
        try:
            if len(self._pending):
                self._exchange("audio", np.ascontiguousarray(self._pending), timeout=10)
            return self._exchange("finish")
        finally:
            self._active = False
            self._pending = np.empty(0, dtype=np.float32)

    def abort_session(self) -> None:
        active, self._active = self._active, False
        self._pending = np.empty(0, dtype=np.float32)
        if active and self._connection is not None:
            self._exchange("abort", timeout=2)

    def _stop_worker(self) -> None:
        connection, self._connection = self._connection, None
        process, self._process = self._process, None
        self.loaded_model = ""
        self._active = False
        self._pending = np.empty(0, dtype=np.float32)
        if connection is not None:
            connection.close()
        if process is not None:
            try:
                process.wait(timeout=.2)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)

    def close(self) -> None:
        try:
            if self._connection is not None and self._process.poll() is None:
                self._exchange("close", timeout=2)
        except RuntimeError:
            pass
        finally:
            self._stop_worker()


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "--nemotron-worker":
        raise SystemExit("This module is an internal VoicePrompt worker.")
    run_worker(int(sys.argv[2]), sys.argv[3])
