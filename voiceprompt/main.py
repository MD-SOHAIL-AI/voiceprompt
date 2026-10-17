from __future__ import annotations

import argparse
import copy
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from voiceprompt.audio import RNNoise
from voiceprompt.cleanup import CloudCleanup
from voiceprompt.config import Settings, config_dir, history_path, load_settings, save_settings
from voiceprompt.diagnostics import Diagnostics
from voiceprompt.history import TranscriptionHistory
from voiceprompt.hotkeys import PushToTalkHotkey
from voiceprompt.instance import SingleInstance
from voiceprompt.injector import TextInjector
from voiceprompt.recorder import PushToTalkRecorder, RecorderConfig
from voiceprompt.replacements import apply_replacements
from voiceprompt.session import DictationSession, IncompleteRecording
from voiceprompt.startup import set_startup, startup_enabled
from voiceprompt.backend_process import create_managed_transcriber as create_transcriber
from voiceprompt.ui import FloatingPill, TrayApp
from voiceprompt.worker import AudioWorkerContext
from voiceprompt.planner import PlannerService
from voiceprompt.state import SessionState, StopReason
from voiceprompt.windows import foreground_window, modifiers_down
from voiceprompt.sounds import SoundFeedback


class VoicePromptApp:
    """One worker owns model/capture operations; hotkey callbacks only signal work."""

    def __init__(self, preload_model: bool | None = None) -> None:
        self.settings = load_settings()
        self.settings.startup_on_boot = startup_enabled()
        if self.settings.startup_on_boot:
            set_startup(True)  # Refresh an existing startup entry to use the local environment.
        save_settings(self.settings)
        self.status = "idle"
        self.last_error = ""
        self.detail = "Prepare your microphone and model to begin."
        self.latest_text = ""
        self.elapsed_seconds = 0.0
        self.backlog_seconds = 0.0
        self.download_progress = {}
        self._failed_audio = None
        self._preparation_cancelled = False
        self._control = threading.RLock()
        self._audio_worker = AudioWorkerContext()
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="dictation", initializer=self._audio_worker.initialize,
        )
        self._working = False
        self._ready = False
        self._quitting = False
        self._current_id = 0
        self._session: DictationSession | None = None
        self._pending_settings: Settings | None = None
        self.sounds = SoundFeedback()
        self._planner_error = ""
        try:
            self.planner = PlannerService(config_dir() / "planner.sqlite3")
        except Exception as exc:
            # A corrupt or unavailable optional Planner must not prevent voice typing.
            self.planner = None
            self._planner_error = f"Planner storage could not open ({type(exc).__name__}). Your existing data has been kept."
        self._planner_ui = None
        self.recorder = self._new_recorder(self.settings)
        self.transcriber = create_transcriber(self.settings)
        self.injector = TextInjector(preserve_clipboard=self.settings.preserve_clipboard)
        self.cleanup = self._new_cleanup(self.settings)
        self.history = TranscriptionHistory(history_path(), limit=self.settings.max_history)
        self.latest_text = self.history.last()
        self.diagnostics = Diagnostics(config_dir())
        self.hotkey = self._new_hotkey(self.settings)
        self.pill = FloatingPill(
            get_settings=lambda: self.settings, on_open_settings=self.open_settings,
            on_retry=self.retry_last, on_quit=self.quit, on_moved=self.update_pill_position,
            on_planner=self.open_planner, on_root_ready=self._planner_root_ready,
            controller=self,
        )
        self.tray = TrayApp(
            get_status=self.get_status, get_last_error=lambda: self.last_error,
            get_settings=lambda: self.settings, on_settings_saved=self.update_settings,
            on_retry=self.retry_last, on_toggle_cleanup=self.toggle_cleanup,
            on_toggle_startup=self.toggle_startup, on_preload_model=self.preload_model,
            on_quit=self.quit, get_runtime_info=self.runtime_info,
            on_planner=self.open_planner,
            controller=self,
        )
        if (self.settings.preload_model and self.settings.onboarding_completed) if preload_model is None else preload_model:
            self.preload_model()

    def run(self) -> None:
        self.hotkey.start()
        self.tray.run_detached()
        self.pill.run()

    def _planner_root_ready(self, root) -> None:
        if self.planner is not None:
            self.planner.start()

    def open_planner(self) -> None:
        self.pill.show_page("Tasks")

    def _reminder_audio_busy(self) -> bool:
        # Keep alert sounds away from microphone capture and the stop cue/paste.
        return self._quitting or self._session is not None or self.recorder.is_recording

    def _play_reminder_sound(self) -> bool:
        with self._control:
            if self._reminder_audio_busy():
                return False
            self.sounds.play("reminder")
            return True

    def quit(self) -> None:
        with self._control:
            if self._quitting:
                return
            self._quitting = True
            self._current_id += 1
            if self._session is not None:
                self._session.cancel.set()
                self._session.request_release(StopReason.CANCELLED)
        self.transcriber.interrupt()
        self._failed_audio = None
        self.hotkey.stop()
        self.tray.stop()
        if self.planner is not None:
            self.planner.request_stop()
        self.pill.call(lambda: self._planner_ui.close() if self._planner_ui else None)
        self.sounds.close()
        self.pill.stop()
        self._executor.submit(self._close_resources)
        self._executor.shutdown(wait=False)

    def _close_resources(self) -> None:
        try:
            if self.planner is not None:
                self.planner.close()
            try:
                self.recorder.close()
            finally:
                self.transcriber.close()
                self.injector.cancel_restore()
                self.diagnostics.close()
        finally:
            self._audio_worker.close()

    def get_status(self) -> str:
        with self._control:
            return self.status

    def set_status(self, status: str, session_id: int | None = None) -> None:
        with self._control:
            if self._quitting or (session_id is not None and session_id != self._current_id):
                return
            self.status = status
            self.pill.set_status(status)
            self.tray.refresh()

    def runtime_info(self) -> str:
        model = self.transcriber.loaded_model or "not loaded"
        info = f"{self.transcriber.backend_name}: {model}"
        if self.transcriber.fallback_reason:
            info += f" | Fallback: {self.transcriber.fallback_reason}"
        if self.recorder.host_api:
            info += f" | {self.recorder.host_api}, {self.recorder.sample_rate} Hz"
        if self.recorder.fallback_reason:
            info += f" | Capture fallback: {self.recorder.fallback_reason}"
        if self._pending_settings is not None:
            info += " | Settings waiting for this session to finish"
        return info

    def open_settings(self) -> None:
        self.pill.show_page("Settings")

    def _begin_work(self) -> int:
        self._working = True
        self._current_id += 1
        return self._current_id

    def preload_model(self) -> None:
        with self._control:
            if self._working or self._quitting:
                return
            sid = self._begin_work()
            self.last_error = ""
            self._preparation_cancelled = False
            self.detail = "Preparing model and microphone. Speak after Ready appears."
            self.set_status("loading model", sid)
            self._executor.submit(self._preload_worker, sid)

    def _prepare(self) -> None:
        self.transcriber.progress = self._download_progress
        self.transcriber.preload()
        if self._preparation_cancelled or self._quitting:
            raise RuntimeError("Preparation cancelled. Select Prepare to try again.")
        self.recorder.prepare()
        if self.settings.noise_suppression:
            RNNoise().close()
        self._ready = True

    def _preload_worker(self, sid: int) -> None:
        started = time.perf_counter()
        try:
            self._prepare()
            self.last_error = ""
            self.download_progress = {}
            self.detail = "Hold your recording key, speak, then release to paste."
            self.diagnostics.record(
                "ready", backend=self.transcriber.backend_name, model=self.transcriber.loaded_model,
                warmup_seconds=time.perf_counter() - started,
                capture_open_seconds=self.recorder.capture_open_seconds,
                input_latency_seconds=self.recorder.input_latency_seconds,
                capture_host_api=self.recorder.host_api,
                model_fallback=bool(self.transcriber.fallback_reason),
                capture_fallback=bool(self.recorder.fallback_reason),
            )
        except Exception as exc:
            self._ready = False
            self._record_error(exc)
        finally:
            self._complete_work(sid)

    def start_recording(self) -> None:
        with self._control:
            if self._working or self._quitting:
                return
            if not self._ready:
                # A cold model must become ready before accepting speech.
                self.preload_model()
                return
            sid = self._begin_work()
            self.last_error = ""
            self._failed_audio = None
            self.elapsed_seconds = self.backlog_seconds = 0.0
            session = DictationSession(sid)
            session.target_window = foreground_window()
            self._session = session
            self.sounds.stop()  # Do not capture a reminder that was already playing.
            settings = copy.deepcopy(self.settings)
            self.detail = "Starting microphone…"
            self.set_status(SessionState.STARTING.value, sid)
            self._executor.submit(self._dictation_worker, session, settings)

    def stop_recording(self) -> None:
        with self._control:
            if self._session is None or self._session.release.is_set():
                return
            self._session.request_release()
            self.set_status("transcribing", self._session.session_id)

    def _hotkey_pressed(self) -> None:
        if self.settings.recording_mode == "toggle" and self._session is not None and not self._session.release.is_set():
            self.stop_recording()
        else:
            self.start_recording()

    def _hotkey_released(self) -> None:
        if self.settings.recording_mode == "ptt":
            self.stop_recording()

    def _dictation_worker(self, session: DictationSession, settings: Settings) -> None:
        sid = session.session_id
        outcome = "error"
        try:
            text, duration = session.run(
                self.recorder, self.transcriber, hotwords=self._hotwords(settings),
                noise_suppression=settings.noise_suppression,
                on_recording_started=lambda: self._recording_cue("start", session, settings),
                on_recording_stopped=lambda: self._recording_cue("stop", session, settings),
                on_progress=lambda elapsed, backlog, failed: self._recording_progress(session, elapsed, backlog, failed),
            )
            if session.cancel.is_set():
                return
            self.set_status("transcribing", sid)
            source = self.transcriber.backend_name
            if text.strip() and self.cleanup.enabled and self.cleanup.available:
                self.set_status("cleaning", sid)
                text = self.cleanup.clean(text)
                source += f"+{settings.cleanup_provider}"
            text = apply_replacements(text, settings.replacements)
            # Guard final insertion against quit/stale workers. Never paste partials.
            with self._control:
                if self._quitting or sid != self._current_id or session.cancel.is_set():
                    return
                if text.strip():
                    self.latest_text = text
                    self.history.add(text, duration_seconds=duration, source=source)
            if text.strip() and settings.paste_injection:
                self.detail = "Release the recording key and any modifiers to finish pasting."
                while getattr(self.hotkey, "pressed", False) is True or modifiers_down():
                    if self._quitting or session.cancel.wait(0.02):
                        return
                with self._control:
                    if self._quitting or session.cancel.is_set() or sid != self._current_id:
                        return
                    if not session.target_window or foreground_window() == session.target_window:
                        pasted_at = self.injector.inject(text)
                        session.metrics["release_to_paste_seconds"] = pasted_at - session.released_at
                        outcome = "pasted"
                        self.detail = "Text pasted. Hold your recording key to dictate again."
                    else:
                        outcome = "text"
                        self.detail = "Text ready. The active window changed; use Copy to insert it where you want."
            else:
                outcome = "text" if text.strip() else "empty"
                self.detail = "Text ready to copy." if text.strip() else "No speech detected. Check your microphone and try again."
            self.last_error = ""
            if session.stop_reason == StopReason.DURATION_LIMIT:
                self.detail = "Five-minute recording limit reached. " + self.detail
            session.audio_queue.clear()
        except Exception as exc:
            if not self._quitting:
                self._record_error(exc)
            outcome = "incomplete" if isinstance(exc, IncompleteRecording) else "error"
            if session.stop_reason not in {StopReason.CANCELLED, StopReason.CAPTURE_FAILED}:
                self._failed_audio = session.audio_queue.retained() or None
            if session.metrics.get("capture_failed"):
                self._ready = False
                self.recorder.close()
            if not isinstance(exc, IncompleteRecording) or session.stop_reason in {StopReason.RECOGNITION_FAILED, StopReason.TIMEOUT}:
                self._ready = False
        finally:
            self.diagnostics.record(
                "dictation", session_id=sid, backend=self.transcriber.backend_name,
                model=self.transcriber.loaded_model, noise_suppression=settings.noise_suppression,
                outcome=outcome, **session.metrics,
            )
            self._complete_work(sid)

    def _recording_cue(self, cue: str, session: DictationSession, settings: Settings) -> None:
        with self._control:
            if self._quitting or session.cancel.is_set() or session.session_id != self._current_id:
                return
            if settings.sound_feedback:
                self.sounds.play(cue)
            if cue == "start":
                self.detail = "Listening. Release your recording key to finish."
                self.set_status(SessionState.LISTENING.value, session.session_id)
            else:
                self.detail = "Finishing the complete recording…"
                self.set_status(SessionState.FINISHING.value, session.session_id)

    def _recording_progress(self, session, elapsed, backlog, failed):
        with self._control:
            if session.session_id != self._current_id or self._quitting or session.release.is_set():
                return
            self.elapsed_seconds, self.backlog_seconds = elapsed, backlog
            state = SessionState.CATCHING_UP if backlog >= 2 or failed else SessionState.LISTENING
            if failed:
                self.detail = "Listening. Recognition stopped; release the key, then retry your recording."
            elif elapsed >= session.max_seconds - 10:
                self.detail = f"Recording ends in {max(0, int(session.max_seconds - elapsed))} seconds at the five-minute limit."
            elif backlog >= 2:
                self.detail = f"Listening — processing behind by {backlog:.1f}s. Your audio is being kept."
            else:
                self.detail = "Listening. Release your recording key to finish."
            if self.status != state.value:
                self.set_status(state.value, session.session_id)

    def _download_progress(self, value):
        self.download_progress = value
        self.detail = value.get("phase", "Preparing model")

    def _complete_work(self, sid: int) -> None:
        with self._control:
            if self._quitting or sid != self._current_id:
                return
            self._working = False
            self._session = None
            pending, self._pending_settings = self._pending_settings, None
            if pending is not None:
                self.update_settings(pending)
            else:
                self.set_status("error" if self.last_error else "ready" if self._ready else "idle", sid)

    def cancel_current(self):
        with self._control:
            if self._session is not None:
                self._session.cancel.set()
                self._session.request_release(StopReason.CANCELLED)
            elif self._working:
                self._preparation_cancelled = True
            self.detail = "Cancelling…"
        threading.Thread(target=self.transcriber.interrupt, name="cancel-recognition", daemon=True).start()

    def discard_failed(self):
        self._failed_audio = None
        self.last_error = ""
        self.detail = "Recording discarded. Prepare the model or start a new recording."
        self.set_status("ready" if self._ready else "idle")

    def retry_failed(self):
        with self._control:
            if self._working or self._quitting or not self._failed_audio:
                return
            sid = self._begin_work()
            chunks = self._failed_audio
            self.last_error = ""
            self.set_status("transcribing", sid)
            self.detail = "Retrying the saved recording. The microphone is off."
            self._executor.submit(self._retry_audio_worker, sid, chunks)

    def _retry_audio_worker(self, sid, chunks):
        from voiceprompt.session import ReplayRecorder
        session = DictationSession(sid)
        self._session = session
        try:
            self.transcriber.preload()
            text, duration = session.run(ReplayRecorder(chunks, session), self.transcriber,
                                         hotwords=self._hotwords(self.settings), noise_suppression=self.settings.noise_suppression)
            text = apply_replacements(text, self.settings.replacements)
            if not self._quitting and not session.cancel.is_set():
                self.latest_text = text
                if text.strip():
                    self.history.add(text, duration, self.transcriber.backend_name)
                self._failed_audio = None
                self.detail = "Recording recovered. Use Copy to insert the text." if text else "No speech detected in the recovered recording."
        except Exception as exc:
            if not self._quitting:
                self._record_error(exc)
        finally:
            self.diagnostics.record("retry", session_id=sid, **session.metrics)
            self._complete_work(sid)

    def check_microphone(self):
        with self._control:
            if self._working or self._quitting:
                return
            sid = self._begin_work()
            self._preparation_cancelled = False
            self.detail = "Speak for three seconds to check your input level. No audio is saved."
            self.set_status("starting", sid)
            self._executor.submit(self._microphone_worker, sid)

    def _microphone_worker(self, sid):
        try:
            self.recorder.prepare()
            self.recorder.start()
            deadline = time.monotonic() + 3
            peak = 0.0
            while time.monotonic() < deadline and not self._quitting and not self._preparation_cancelled:
                peak = max(peak, self.recorder.level)
                time.sleep(0.02)
            self.recorder.stop(grace=False)
            self.detail = "Microphone works. Next, prepare the speech model." if peak > 0.005 else "Input is very quiet. Check the selected microphone and your distance."
            self.last_error = ""
        except Exception as exc:
            self._record_error(exc)
        finally:
            if self.recorder.is_recording:
                self.recorder.stop(grace=False)
            self._complete_work(sid)

    def retry_last(self) -> None:
        with self._control:
            if self._working or self._quitting:
                return
            sid = self._begin_work()
            self._executor.submit(self._retry_worker, sid)

    def _retry_worker(self, sid: int) -> None:
        try:
            text = self.history.last()
            with self._control:
                if text and not self._quitting and sid == self._current_id:
                    self.injector.inject(text)
        except Exception as exc:
            self._record_error(exc)
        finally:
            self._complete_work(sid)

    def toggle_cleanup(self) -> None:
        with self._control:
            settings = self._pending_settings or self.settings
            provider = "none" if settings.cleanup_provider != "none" else "openrouter"
            self.update_settings(replace(settings, cleanup_provider=provider))

    def toggle_startup(self) -> None:
        with self._control:
            settings = self._pending_settings or self.settings
            self.update_settings(replace(settings, startup_on_boot=not settings.startup_on_boot))

    def update_settings(self, settings: Settings) -> None:
        with self._control:
            if self._quitting:
                return
            if self._working:
                self._pending_settings = copy.deepcopy(settings)
                self.tray.refresh()
                return
            sid = self._begin_work()
            self.set_status("loading model", sid)
            self._executor.submit(self._apply_settings_worker, copy.deepcopy(settings), sid)

    def _apply_settings_worker(self, settings: Settings, sid: int) -> None:
        try:
            old = self.settings
            settings.config_version = 6
            if settings.backend in {"moonshine", "parakeet", "nemotron"}:
                settings.language = "en"
            settings.gemini_cleanup = settings.cleanup_provider == "gemini"
            settings.pill_position_x = old.pill_position_x
            settings.pill_position_y = old.pill_position_y
            if settings.startup_on_boot != old.startup_on_boot:
                set_startup(settings.startup_on_boot)
            model_changed = any(getattr(old, k) != getattr(settings, k) for k in (
                "backend", "model", "streaming_model", "device", "compute_type", "cpu_threads",
                "nemotron_device",
            ))
            capture_changed = any(getattr(old, k) != getattr(settings, k) for k in (
                "microphone", "capture_mode", "noise_suppression",
            ))
            if model_changed:
                self.transcriber.close()
                self.transcriber = create_transcriber(settings)
                self._ready = False
            elif settings.backend == "whisper":
                self.transcriber.update_options(settings.language, settings.beam_size, settings.vad_filter)
            if capture_changed:
                self.recorder.close()
                self.recorder = self._new_recorder(settings)
                self._ready = False
            with self._control:
                self.settings = settings
                save_settings(settings)
            self.injector.cancel_restore()
            self.injector = TextInjector(preserve_clipboard=settings.preserve_clipboard)
            self.cleanup = self._new_cleanup(settings)
            self.history.limit = settings.max_history
            if settings.hotkey != old.hotkey:
                self.hotkey.stop()
                self.hotkey = self._new_hotkey(settings)
                self.hotkey.start()
            if settings.preload_model or self._ready:
                self._prepare()
            self.last_error = ""
        except Exception as exc:
            self._ready = False
            self._record_error(exc)
        finally:
            self._complete_work(sid)

    def update_pill_position(self, x: int, y: int) -> None:
        with self._control:
            self.settings.pill_position_x = x
            self.settings.pill_position_y = y
            save_settings(self.settings)

    def _new_hotkey(self, settings: Settings) -> PushToTalkHotkey:
        return PushToTalkHotkey(settings.hotkey, self._hotkey_pressed, self._hotkey_released)

    @staticmethod
    def _new_recorder(settings: Settings) -> PushToTalkRecorder:
        return PushToTalkRecorder(RecorderConfig(
            sample_rate=48000 if settings.noise_suppression else 16000,
            microphone=settings.microphone, capture_mode=settings.capture_mode, retain_audio=False,
        ))

    @staticmethod
    def _new_cleanup(settings: Settings) -> CloudCleanup:
        return CloudCleanup(settings.cleanup_provider, settings.openrouter_model, settings.gemini_model, settings.cleanup_timeout_seconds)

    @staticmethod
    def _hotwords(settings: Settings) -> str:
        terms = []
        terms += [value.strip() for value in settings.replacements.values() if value.strip()]
        return ", ".join(dict.fromkeys(terms))

    def _record_error(self, exc: Exception) -> None:
        self.last_error = f"{type(exc).__name__}: {exc}"
        self.detail = self.last_error
        (config_dir() / "voiceprompt.log").write_text(traceback.format_exc(), encoding="utf-8")
        self.tray.refresh()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VoicePrompt local push-to-talk dictation")
    preload = parser.add_mutually_exclusive_group()
    preload.add_argument("--preload", dest="preload", action="store_true", help="Warm the model at startup")
    preload.add_argument("--no-preload", dest="preload", action="store_false", help="Warm the model on the first hotkey press")
    parser.set_defaults(preload=None)
    return parser.parse_args()


def main() -> None:
    import sys

    if len(sys.argv) == 4 and sys.argv[1] == "--nemotron-worker":
        from voiceprompt.nemotron_process import run_worker

        run_worker(int(sys.argv[2]), sys.argv[3])
        return
    args = parse_args()
    with SingleInstance() as instance:
        if instance.already_running:
            return
        app = VoicePromptApp(preload_model=args.preload)
        try:
            app.run()
        finally:
            app.quit()
            app._executor.shutdown(wait=True)


if __name__ == "__main__":
    main()
