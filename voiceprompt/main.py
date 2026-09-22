from __future__ import annotations

import argparse
import threading
import time
import traceback
from dataclasses import replace

import numpy as np

from voiceprompt.cleanup import CloudCleanup
from voiceprompt.config import Settings, config_dir, history_path, load_settings, save_settings
from voiceprompt.history import TranscriptionHistory
from voiceprompt.hotkeys import PushToTalkHotkey
from voiceprompt.instance import SingleInstance
from voiceprompt.injector import TextInjector, capture_foreground_window
from voiceprompt.recorder import PushToTalkRecorder, RecorderConfig, Recording
from voiceprompt.replacements import apply_replacements
from voiceprompt.sound_feedback import SoundFeedback
from voiceprompt.startup import set_startup, startup_enabled
from voiceprompt.transcriber import LocalTranscriber
from voiceprompt.ui import FloatingPill, TrayApp


class VoicePromptApp:
    def __init__(self, preload_model: bool | None = None) -> None:
        self.settings = load_settings()
        self.settings.startup_on_boot = startup_enabled()
        save_settings(self.settings)

        self.status = "idle"
        self.last_error = ""
        self._last_text = ""
        self._record_target: int | None = None
        self._status_lock = threading.Lock()
        self._busy_lock = threading.Lock()

        self.recorder = self._new_recorder(self.settings)
        self.transcriber = self._new_transcriber(self.settings)
        self.injector = self._new_injector(self.settings)
        self.cleanup = self._new_cleanup(self.settings)
        self.sound = SoundFeedback(enabled=self.settings.sound_feedback)
        self.history = TranscriptionHistory(history_path(), limit=self.settings.max_history)
        self.hotkey = PushToTalkHotkey(self.settings.hotkey, self._hotkey_pressed, self._hotkey_released)
        self.pill = FloatingPill(
            get_settings=lambda: self.settings,
            on_open_settings=self.open_settings,
            on_retry=self.retry_last,
            on_quit=self.quit,
            on_moved=self.update_pill_position,
        )
        self.tray = TrayApp(
            get_status=self.get_status,
            get_last_error=lambda: self.last_error,
            get_settings=lambda: self.settings,
            on_open_settings=self.open_settings,
            on_retry=self.retry_last,
            on_clear_history=self.clear_history,
            on_toggle_cleanup=self.toggle_cleanup,
            on_toggle_startup=self.toggle_startup,
            on_toggle_sound=self.toggle_sound,
            on_preload_model=self.preload_model,
            on_quit=self.quit,
        )

        should_preload = self.settings.preload_model if preload_model is None else preload_model
        if should_preload:
            self.preload_model()

    def run(self) -> None:
        self.hotkey.start()
        self.tray.run_detached()
        self.pill.run()

    def quit(self) -> None:
        self.hotkey.stop()
        self.tray.stop()
        self.pill.stop()

    def get_status(self) -> str:
        with self._status_lock:
            return self.status

    def set_status(self, status: str) -> None:
        with self._status_lock:
            self.status = status
        self._publish_status(status)

    def _transition_status(self, allowed: set[str], status: str) -> str | None:
        with self._status_lock:
            previous = self.status
            if previous not in allowed:
                return None
            self.status = status
        self._publish_status(status)
        return previous

    def _publish_status(self, status: str) -> None:
        self.pill.set_status(status)
        self.tray.refresh()

    def open_settings(self) -> None:
        self.pill.open_settings_window(self.update_settings)

    def preload_model(self) -> None:
        previous = self._transition_status({"idle", "ready"}, "loading model")
        if previous is not None:
            threading.Thread(target=self._preload_model_worker, args=(previous,), daemon=True).start()

    def start_recording(self) -> None:
        if self._transition_status({"idle", "ready"}, "recording") is None:
            return
        self._record_target = capture_foreground_window()
        try:
            # Finish the activation cue before the microphone opens so the
            # cue itself cannot leak into transcription.
            self.sound.play_active()
            self.recorder.start()
        except Exception as exc:
            self._record_error(exc)
            self.set_status("idle")

    def stop_recording(self) -> None:
        if self.get_status() != "recording" or not self.recorder.is_recording:
            return
        target_window = self._record_target
        try:
            recording = self.recorder.stop()
            # recorder.stop() includes final-phoneme grace and fully closes the
            # microphone before this cue is played.
            self.sound.play_inactive(asynchronous=True)
        except Exception as exc:
            self._record_error(exc)
            self.set_status("idle")
            return

        if recording is None:
            self.set_status("idle")
            return

        threading.Thread(
            target=self._transcribe_and_inject,
            args=(recording, target_window),
            daemon=True,
        ).start()

    def _hotkey_pressed(self) -> None:
        if self.settings.recording_mode == "toggle" and self.get_status() == "recording":
            self.stop_recording()
        else:
            self.start_recording()

    def _hotkey_released(self) -> None:
        if self.settings.recording_mode == "ptt":
            self.stop_recording()

    def retry_last(self) -> None:
        text = self._last_text or (self.history.last() if self.settings.save_history else "")
        if text:
            self.injector.inject(text, capture_foreground_window())

    def clear_history(self) -> None:
        self.history.clear()
        self._last_text = ""
        self.tray.refresh()

    def toggle_cleanup(self) -> None:
        if self.settings.cleanup_provider != "none":
            provider = self.settings.cleanup_provider
            self.update_settings(replace(self.settings, cleanup_provider="none", last_cleanup_provider=provider))
        else:
            self.update_settings(replace(self.settings, cleanup_provider=self.settings.last_cleanup_provider))

    def toggle_sound(self) -> None:
        self.update_settings(replace(self.settings, sound_feedback=not self.settings.sound_feedback))

    def toggle_startup(self) -> None:
        self.update_settings(replace(self.settings, startup_on_boot=not self.settings.startup_on_boot))

    def update_settings(self, settings: Settings) -> None:
        transcriber_changed = any((
            settings.asr_backend != self.settings.asr_backend,
            settings.model != self.settings.model,
            settings.device != self.settings.device,
            settings.compute_type != self.settings.compute_type,
            settings.whisper_cpp_executable != self.settings.whisper_cpp_executable,
            settings.whisper_cpp_model != self.settings.whisper_cpp_model,
            settings.whisper_cpp_threads != self.settings.whisper_cpp_threads,
        ))
        recorder_changed = (
            settings.input_device != self.settings.input_device
            or settings.max_recording_seconds != self.settings.max_recording_seconds
        )
        hotkey_changed = settings.hotkey != self.settings.hotkey
        startup_changed = settings.startup_on_boot != self.settings.startup_on_boot

        if startup_changed:
            try:
                set_startup(settings.startup_on_boot)
            except Exception as exc:
                self._record_error(exc)

        if settings.cleanup_provider != "none":
            settings.last_cleanup_provider = settings.cleanup_provider
        self.settings = settings
        self.settings.gemini_cleanup = settings.cleanup_provider == "gemini"
        save_settings(settings)
        self.sound.set_enabled(settings.sound_feedback)
        self.injector = self._new_injector(settings)
        self.cleanup = self._new_cleanup(settings)
        self.history.limit = settings.max_history

        if recorder_changed:
            self.recorder = self._new_recorder(settings)

        if transcriber_changed:
            self.transcriber = self._new_transcriber(settings)
            self.set_status("idle")
            if settings.preload_model:
                self.preload_model()
        else:
            self.transcriber.update_options(settings.language, settings.beam_size, settings.vad_filter)

        if hotkey_changed:
            self.hotkey.stop()
            self.hotkey = PushToTalkHotkey(settings.hotkey, self._hotkey_pressed, self._hotkey_released)
            self.hotkey.start()

        self.tray.refresh()

    def update_pill_position(self, x: int, y: int) -> None:
        self.settings.pill_position_x = x
        self.settings.pill_position_y = y
        save_settings(self.settings)

    def _new_recorder(self, settings: Settings) -> PushToTalkRecorder:
        device: int | str | None = settings.input_device.strip() or None
        if isinstance(device, str) and device.isdigit():
            device = int(device)
        recorder = PushToTalkRecorder(
            RecorderConfig(max_seconds=settings.max_recording_seconds, input_device=device)
        )
        recorder.on_audio_chunk = self._on_audio_chunk
        recorder.on_max_duration = self.stop_recording
        return recorder

    def _new_injector(self, settings: Settings) -> TextInjector:
        return TextInjector(
            preserve_clipboard=settings.preserve_clipboard,
            restore_focus_on_paste=settings.restore_focus_on_paste,
        )

    def _new_transcriber(self, settings: Settings) -> LocalTranscriber:
        return LocalTranscriber(
            backend=settings.asr_backend,
            model_name=settings.model,
            language=settings.language,
            device=settings.device,
            compute_type=settings.compute_type,
            beam_size=settings.beam_size,
            vad_filter=settings.vad_filter,
            whisper_cpp_executable=settings.whisper_cpp_executable,
            whisper_cpp_model=settings.whisper_cpp_model,
            whisper_cpp_threads=settings.whisper_cpp_threads,
        )

    @staticmethod
    def _new_cleanup(settings: Settings) -> CloudCleanup:
        return CloudCleanup(
            provider=settings.cleanup_provider,
            openrouter_model=settings.openrouter_model,
            gemini_model=settings.gemini_model,
            timeout_seconds=settings.cleanup_timeout_seconds,
        )

    def _hotwords(self) -> str:
        built_in_terms = [
            "ChatGPT", "Claude Code", "Gemini", "OpenRouter", "ESP32", "GPIO", "C++", "ForgeX", "embedded systems"
        ]
        terms = built_in_terms + [value.strip() for value in self.settings.replacements.values() if value.strip()]
        return ", ".join(dict.fromkeys(terms))

    def _on_audio_chunk(self, audio: np.ndarray) -> None:
        if audio.size == 0:
            return
        rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float32, copy=False)))))
        self.pill.set_audio_level(min(1.0, rms * 10.0))

    def _preload_model_worker(self, previous: str) -> None:
        try:
            self.transcriber.preload()
            self.last_error = ""
            self.set_status("ready")
        except Exception as exc:
            self._record_error(exc)
            self.set_status(previous)

    def _transcribe_and_inject(self, recording: Recording, target_window: int | None) -> None:
        if not self._busy_lock.acquire(blocking=False):
            self.set_status("idle")
            return

        started = time.perf_counter()
        try:
            self.set_status("transcribing")
            text = self.transcriber.transcribe(recording.audio, hotwords=self._hotwords())
            source = f"local:{self.transcriber.engine_name}"

            if self.cleanup.enabled and self.cleanup.available and text.strip():
                self.set_status("cleaning")
                cleanup_result = self.cleanup.clean(text)
                text = cleanup_result.text
                if cleanup_result.applied:
                    source += f"+{cleanup_result.provider}"
                if cleanup_result.error:
                    print(f"Cleanup fallback: {cleanup_result.error}")

            text = apply_replacements(text, self.settings.replacements)
            if text.strip():
                self._last_text = text
                if self.settings.save_history:
                    self.history.add(text, duration_seconds=recording.duration_seconds, source=source)
                if self.settings.paste_injection:
                    pasted = self.injector.inject(text, target_window)
                    if not pasted:
                        self.last_error = "Paste skipped because the original target window is no longer focused. Use Retry last transcription."

            if not self.last_error.startswith("Paste skipped"):
                self.last_error = ""
            elapsed = time.perf_counter() - started
            print(f"Transcribed with {self.transcriber.engine_name} in {elapsed:.2f}s: {text}")
        except Exception as exc:
            self._record_error(exc)
        finally:
            self._busy_lock.release()
            self.pill.set_audio_level(0.0)
            self.set_status("idle")

    def _record_error(self, exc: Exception) -> None:
        self.last_error = f"{type(exc).__name__}: {exc}"
        log_path = config_dir() / "prompt_voice.log"
        try:
            log_path.write_text(traceback.format_exc(), encoding="utf-8")
        except OSError:
            pass
        print(self.last_error)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Voice Prompt local push-to-talk dictation")
    preload = parser.add_mutually_exclusive_group()
    preload.add_argument("--preload", dest="preload", action="store_true", help="Load ASR model at startup")
    preload.add_argument("--no-preload", dest="preload", action="store_false", help="Load ASR model on first use")
    parser.set_defaults(preload=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with SingleInstance() as instance:
        if instance.already_running:
            return
        app = VoicePromptApp(preload_model=args.preload)
        app.run()


if __name__ == "__main__":
    main()
