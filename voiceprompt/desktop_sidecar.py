"""JSON-lines bridge between the Tauri desktop shell and the hardened Voice Prompt engine.

The bridge deliberately owns no UI.  It validates every command, emits structured events,
and reuses the existing recorder/transcriber/injector implementation so V2 does not fork
core dictation behavior.
"""
from __future__ import annotations

import json
import queue
import sys
import threading
import time
import traceback
from dataclasses import asdict
from typing import Any

from voiceprompt.config import Settings
from voiceprompt.injector import TextInjector
from voiceprompt.recorder import AudioRecorder
from voiceprompt.replacements import apply_replacements
from voiceprompt.sound_feedback import SoundFeedback
from voiceprompt.transcriber import LocalTranscriber

_MAX_LINE = 256 * 1024
_ALLOWED = {"configure", "start", "stop", "shutdown", "ping"}


class DesktopEngine:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._profile: dict[str, Any] = {}
        self._recorder: AudioRecorder | None = None
        self._transcriber: LocalTranscriber | None = None
        self._injector = TextInjector()
        self._sound = SoundFeedback(True)
        self._started_at = 0.0
        self._busy = False

    def emit(self, kind: str, **payload: Any) -> None:
        message = {"kind": kind, **payload}
        sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def configure(self, profile: dict[str, Any]) -> None:
        with self._lock:
            self._profile = dict(profile)
            self._sound.set_enabled(bool(profile.get("soundFeedback", True)))
            self._transcriber = None
        self.emit("ready")

    def _settings(self) -> Settings:
        p = self._profile
        return Settings(
            model=str(p.get("transcriptionModel") or "base"),
            language="" if p.get("language", "auto") == "auto" else str(p.get("language", "")),
            recording_mode=str(p.get("recordingMode") or "ptt"),
            sound_feedback=bool(p.get("soundFeedback", True)),
            paste_injection=bool(p.get("autoPaste", True)),
            restore_focus_on_paste=bool(p.get("restoreTargetFocus", True)),
            replacements={str(k): str(v) for k, v in dict(p.get("customReplacements") or {}).items()},
        )

    def start(self) -> None:
        with self._lock:
            if self._busy or self._recorder is not None:
                return
            settings = self._settings()
            self._sound.play_active()
            self._recorder = AudioRecorder(
                input_device=settings.input_device,
                max_recording_seconds=settings.max_recording_seconds,
                on_level=lambda level: self.emit("waveform", level=max(0.0, min(1.0, float(level) * 10.0))),
            )
            self._recorder.start()
            self._started_at = time.perf_counter()
        self.emit("status", status="recording")

    def stop(self) -> None:
        with self._lock:
            recorder = self._recorder
            if recorder is None or self._busy:
                return
            self._recorder = None
            self._busy = True
        try:
            audio = recorder.stop()
            self._sound.play_inactive(asynchronous=True)
        except Exception as exc:
            with self._lock:
                self._busy = False
            self.emit("error", message=f"Recording failed: {exc}")
            self.emit("ready")
            return
        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _process(self, audio: Any) -> None:
        try:
            settings = self._settings()
            self.emit("status", status="transcribing")
            started = time.perf_counter()
            if self._transcriber is None:
                self._transcriber = LocalTranscriber(settings)
            text = self._transcriber.transcribe(audio)
            if not isinstance(text, str):
                text = getattr(text, "text", str(text))
            text = apply_replacements(text.strip(), settings.replacements)
            transcribe_ms = int((time.perf_counter() - started) * 1000)
            if not text:
                raise RuntimeError("No speech was detected.")

            paste_ms = 0
            if settings.paste_injection:
                paste_started = time.perf_counter()
                self._injector.inject(text, restore_clipboard=settings.preserve_clipboard)
                paste_ms = int((time.perf_counter() - paste_started) * 1000)

            total_ms = int((time.perf_counter() - self._started_at) * 1000)
            self.emit(
                "result",
                result={
                    "id": f"local-{time.time_ns()}",
                    "text": text,
                    "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "audioDurationMs": max(0, total_ms - transcribe_ms - paste_ms),
                    "transcriptionMs": transcribe_ms,
                    "cleanupMs": 0,
                    "pasteMs": paste_ms,
                    "totalMs": total_ms,
                    "provider": "local",
                    "model": settings.model,
                    "language": settings.language or "auto",
                    "costUsd": None,
                    "targetApp": None,
                    "source": "local",
                },
            )
            time.sleep(0.25)
            self.emit("ready")
        except Exception as exc:
            self.emit("error", message=str(exc))
            self.emit("ready")
        finally:
            with self._lock:
                self._busy = False

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
