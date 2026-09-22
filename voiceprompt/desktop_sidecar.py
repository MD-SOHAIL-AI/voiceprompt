"""JSON-lines bridge used by the Voice Prompt V2 Tauri shell.

V2 intentionally reuses the hardened recorder, local transcriber, replacements and safe
paste injector instead of maintaining a second dictation implementation.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from typing import Any

import numpy as np

from voiceprompt.injector import TextInjector, capture_foreground_window
from voiceprompt.recorder import PushToTalkRecorder, RecorderConfig, Recording
from voiceprompt.replacements import apply_replacements
from voiceprompt.sound_feedback import SoundFeedback
from voiceprompt.transcriber import LocalTranscriber

_MAX_LINE = 256 * 1024
_ALLOWED = {"configure", "start", "stop", "shutdown", "ping"}


class DesktopEngine:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._profile: dict[str, Any] = {}
        self._recorder: PushToTalkRecorder | None = None
        self._transcriber: LocalTranscriber | None = None
        self._transcriber_key: tuple[str, str] | None = None
        self._sound = SoundFeedback(True)
        self._target_window: int | None = None
        self._busy = False

    def emit(self, kind: str, **payload: Any) -> None:
        sys.stdout.write(json.dumps({"kind": kind, **payload}, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def configure(self, profile: dict[str, Any]) -> None:
        with self._lock:
            self._profile = dict(profile)
            self._sound.set_enabled(bool(profile.get("soundFeedback", True)))
            key = (str(profile.get("transcriptionModel") or "base"), str(profile.get("language") or "auto"))
            if key != self._transcriber_key:
                self._transcriber = None
                self._transcriber_key = key
        self.emit("ready")

    def _local_transcriber(self) -> LocalTranscriber:
        model = str(self._profile.get("transcriptionModel") or "base")
        language = str(self._profile.get("language") or "auto")
        if language == "auto":
            language = ""
        if self._transcriber is None:
            self._transcriber = LocalTranscriber(
                backend="auto",
                model_name=model,
                language=language,
                device="cpu",
                compute_type="int8",
                beam_size=3,
                vad_filter=True,
            )
        return self._transcriber

    def start(self) -> None:
        with self._lock:
            if self._busy or self._recorder is not None:
                return
            self._sound.play_active()
            recorder = PushToTalkRecorder(RecorderConfig(max_seconds=30.0))
            recorder.on_audio_chunk = self._on_audio
            recorder.on_max_duration = self.stop
            recorder.start()
            self._recorder = recorder
            self._target_window = capture_foreground_window()
        self.emit("status", status="recording")

    def _on_audio(self, chunk: np.ndarray) -> None:
        try:
            rms = float(np.sqrt(np.mean(np.square(chunk.astype(np.float64)))))
            self.emit("waveform", level=max(0.0, min(1.0, rms * 10.0)))
        except Exception:
            pass

    def stop(self) -> None:
        with self._lock:
            recorder = self._recorder
            if recorder is None or self._busy:
                return
            self._recorder = None
            self._busy = True
        try:
            recording = recorder.stop()
            self._sound.play_inactive(asynchronous=True)
        except Exception as exc:
            with self._lock:
                self._busy = False
            self.emit("error", message=f"Recording failed: {exc}")
            self.emit("ready")
            return
        if recording is None:
            with self._lock:
                self._busy = False
            self.emit("ready")
            return
        threading.Thread(target=self._process, args=(recording,), daemon=True).start()

    def _process(self, recording: Recording) -> None:
        started = time.perf_counter()
        try:
            mode = str(self._profile.get("engineMode") or "local")
            provider = str(self._profile.get("transcriptionProvider") or "local")
            if mode == "cloud" or (mode == "auto" and provider != "local"):
                raise RuntimeError("Cloud transcription is not enabled in this build yet. Select Local mode.")

            self.emit("status", status="transcribing")
            transcribe_started = time.perf_counter()
            text = self._local_transcriber().transcribe(recording.audio)
            transcribe_ms = int((time.perf_counter() - transcribe_started) * 1000)
            replacements = {str(k): str(v) for k, v in dict(self._profile.get("customReplacements") or {}).items()}
            text = apply_replacements(text.strip(), replacements)
            if not text:
                raise RuntimeError("No speech was detected.")

            paste_ms = 0
            if bool(self._profile.get("autoPaste", True)):
                paste_started = time.perf_counter()
                injector = TextInjector(
                    preserve_clipboard=True,
                    restore_focus_on_paste=bool(self._profile.get("restoreTargetFocus", True)),
                )
                if not injector.inject(text, target_window=self._target_window):
                    raise RuntimeError("The original target window is unavailable; transcript was not pasted.")
                paste_ms = int((time.perf_counter() - paste_started) * 1000)

            total_ms = int((time.perf_counter() - started) * 1000)
            self.emit("result", result={
                "id": f"local-{time.time_ns()}",
                "text": text,
                "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "audioDurationMs": int(recording.duration_seconds * 1000),
                "transcriptionMs": transcribe_ms,
                "cleanupMs": 0,
                "pasteMs": paste_ms,
                "totalMs": total_ms,
                "provider": "local",
                "model": str(self._profile.get("transcriptionModel") or "base"),
                "language": str(self._profile.get("language") or "auto"),
                "costUsd": None,
                "targetApp": None,
                "source": "local",
            })
            time.sleep(0.25)
            self.emit("ready")
        except Exception as exc:
            self.emit("error", message=str(exc))
            self.emit("ready")
        finally:
            with self._lock:
                self._busy = False
                self._target_window = None

    def shutdown(self) -> None:
        with self._lock:
            recorder = self._recorder
            self._recorder = None
        if recorder is not None:
            try:
                recorder.stop()
            except Exception:
                pass


def main() -> int:
    engine = DesktopEngine()
    engine.emit("ready")
    for raw in sys.stdin:
        if len(raw) > _MAX_LINE:
            engine.emit("error", message="Command exceeds maximum size.")
            continue
        try:
            message = json.loads(raw)
            if not isinstance(message, dict):
                raise ValueError("Command must be an object.")
            command = str(message.get("command", ""))
            if command not in _ALLOWED:
                raise ValueError("Unsupported command.")
            if command == "configure":
                profile = message.get("profile")
                if not isinstance(profile, dict):
                    raise ValueError("configure requires a profile object.")
                engine.configure(profile)
            elif command == "start":
                engine.start()
            elif command == "stop":
                engine.stop()
            elif command == "ping":
                engine.emit("ready")
            elif command == "shutdown":
                engine.shutdown()
                return 0
        except Exception as exc:
            engine.emit("error", message=str(exc))
    engine.shutdown()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        sys.stderr.write(traceback.format_exc())
        raise
