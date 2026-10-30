from __future__ import annotations

import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

from voiceprompt.config import Settings
from voiceprompt.main import VoicePromptApp
from voiceprompt.session import DictationSession, IncompleteRecording


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        settings = Settings()
        for name, value in (
            ("load_settings", settings), ("startup_enabled", False), ("config_dir", root),
            ("history_path", root / "history.json"), ("save_settings", None),
            ("foreground_window", 123), ("is_voiceprompt_window", False), ("modifiers_down", False),
        ):
            p = patch(f"voiceprompt.main.{name}", return_value=value)
            p.start()
            self.addCleanup(p.stop)
        p = patch("voiceprompt.main.set_startup")
        p.start()
        self.addCleanup(p.stop)
        p = patch("voiceprompt.credentials.retire_cloud_credentials", return_value="")
        p.start()
        self.addCleanup(p.stop)
        for name in ("FloatingPill", "TrayApp", "PushToTalkHotkey", "TextInjector", "SoundFeedback"):
            p = patch(f"voiceprompt.main.{name}")
            p.start()
            self.addCleanup(p.stop)
        self.backend = MagicMock()
        self.backend.loaded_model = "base.en"
        self.backend.backend_name = "whisper"
        self.backend.fallback_reason = ""
        p = patch("voiceprompt.main.create_transcriber", return_value=self.backend)
        p.start()
        self.addCleanup(p.stop)
        recorder = MagicMock()
        recorder.host_api = "Test"
        recorder.fallback_reason = ""
        recorder.sample_rate = 16000
        p = patch("voiceprompt.main.PushToTalkRecorder", return_value=recorder)
        p.start()
        self.addCleanup(p.stop)
        self.app = VoicePromptApp(preload_model=False)
        self.app.hotkey.pressed = False
        self.app._ready = True
        self.app.injector.inject.side_effect = lambda _, **kwargs: time.perf_counter()
        self.addCleanup(self.close_app)

    def close_app(self):
        self.app.quit()
        self.app._executor.shutdown(wait=True)

    def wait_idle(self):
        deadline = time.perf_counter() + 3
        while self.app._working and time.perf_counter() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.app._working)

    def test_hotkey_release_is_nonblocking_and_inserts_exactly_once(self):
        entered = threading.Event()

        def run(session, *args, **kwargs):
            entered.set()
            session.release.wait(2)
            time.sleep(0.05)
            return "hello", 1.0

        with patch.object(DictationSession, "run", run):
            self.app.start_recording()
            self.assertTrue(entered.wait(2))
            started = time.perf_counter()
            self.app.stop_recording()
            self.assertLess(time.perf_counter() - started, 0.04)
            self.app.stop_recording()
            self.app.start_recording()  # ignored while finalization is in progress
            self.wait_idle()
        self.app.injector.inject.assert_called_once_with("hello", target_window=123, cancelled=ANY)
        self.assertEqual(self.app.history.last(), "hello")

    def test_diagnostics_and_history_failures_do_not_block_dictation(self):
        def run(session, *args, **kwargs):
            session.request_release()
            return "recognized text", 1.0
        with patch.object(DictationSession, "run", run), \
             patch.object(self.app.diagnostics, "record", side_effect=OSError("disk full")), \
             patch.object(self.app.history, "add", side_effect=OSError("disk full")):
            self.app.start_recording()
            self.wait_idle()
        self.app.injector.inject.assert_called_once_with("recognized text", target_window=123, cancelled=ANY)
        self.assertTrue(self.app.storage_warning)
        self.assertTrue(self.app._ready)

    def test_failed_audio_thread_initialization_does_not_leave_busy_state(self):
        from concurrent.futures import ThreadPoolExecutor
        self.app._executor.shutdown(wait=True)
        def broken(): raise RuntimeError("COM failed")
        self.app._executor = ThreadPoolExecutor(max_workers=1, initializer=broken)
        self.app.start_recording()
        self.wait_idle()
        self.assertFalse(self.app._ready)
        self.assertIn("Restart", self.app.last_error)

    def test_capture_failure_invalidates_readiness_and_reopens_capture(self):
        def run(session, *args, **kwargs):
            from voiceprompt.state import StopReason
            session.stop_reason = StopReason.CAPTURE_FAILED
            raise IncompleteRecording("Microphone dropped frames")
        with patch.object(DictationSession, "run", run):
            self.app.start_recording()
            self.wait_idle()
        self.assertFalse(self.app._ready)
        self.app.recorder.close.assert_called()
        self.app.injector.inject.assert_not_called()

    def test_cancel_stays_responsive_while_clipboard_delivery_waits(self):
        entered, release = threading.Event(), threading.Event()
        def run(session, *args, **kwargs):
            session.request_release()
            return "completed text", 1.0
        def inject(text, **kwargs):
            entered.set()
            release.wait(2)
            if kwargs["cancelled"](): raise RuntimeError("cancelled")
            return time.perf_counter()
        self.app.injector.inject.side_effect = inject
        with patch.object(DictationSession, "run", run):
            self.app.start_recording()
            self.assertTrue(entered.wait(2))
            started = time.perf_counter()
            self.app.cancel_current()
            self.assertLess(time.perf_counter() - started, .5)
            release.set()
            self.wait_idle()
        self.assertEqual(self.app.insertion_status, "copy")

    def test_empty_retry_keeps_audio_and_validates_readiness(self):
        import numpy as np
        chunks = ((np.ones(1600, dtype=np.float32), 16000),)
        self.app._failed_audio = chunks
        self.app._ready = False
        with patch.object(DictationSession, "run", return_value=("", .1)):
            self.app.retry_failed()
            self.wait_idle()
        self.assertIs(self.app._failed_audio, chunks)
        self.assertTrue(self.app._ready)

    def test_pending_settings_patches_are_merged(self):
        from voiceprompt.desktop_sidecar import DesktopService
        service = DesktopService(self.app, MagicMock())
        self.app._working = True
        service.dispatch("settings.save", {"settings": {"backend": "moonshine"}})
        service.dispatch("settings.save", {"settings": {"sound_feedback": False}})
        self.assertEqual(self.app._pending_settings.backend, "moonshine")
        self.assertFalse(self.app._pending_settings.sound_feedback)

    def test_failed_paste_keeps_text_and_accepts_next_recording(self):
        def run(session, *args, **kwargs):
            session.request_release()
            return "recognized text", 1.0
        self.app.injector.inject.side_effect = RuntimeError("blocked")
        with patch.object(DictationSession, "run", run):
            self.app.start_recording()
            self.wait_idle()
        self.assertEqual(self.app.latest_text, "recognized text")
        self.assertEqual(self.app.insertion_status, "copy")
        self.assertTrue(self.app._ready)

    def test_settings_wait_for_recording_and_do_not_replace_session_backend(self):
        entered = threading.Event()
        finish = threading.Event()

        def run(session, *args, **kwargs):
            entered.set()
            session.release.wait(2)
            finish.wait(2)
            return "hello", 1.0

        with patch.object(DictationSession, "run", run):
            self.app.start_recording()
            self.assertTrue(entered.wait(2))
            self.app.update_settings(replace(self.app.settings, beam_size=1))
            self.assertEqual(self.app.settings.beam_size, 3)
            self.backend.update_options.assert_not_called()
            self.app.stop_recording()
            finish.set()
            self.wait_idle()
        self.assertEqual(self.app.settings.beam_size, 1)
        self.backend.update_options.assert_called_once_with("en", 1, True)

    def test_held_modifier_does_not_block_future_recordings(self):
        def run(session, *args, **kwargs):
            session.request_release()
            return "all words", 1.0

        with patch.object(DictationSession, "run", run), \
             patch("voiceprompt.main.modifiers_down", return_value=True), \
             patch("voiceprompt.main.time.monotonic", side_effect=[10.0, 13.0]):
            self.app.start_recording()
            self.wait_idle()
        self.app.injector.inject.assert_not_called()
        self.assertEqual(self.app.latest_text, "all words")
        self.assertEqual(self.app.insertion_status, "copy")
        self.assertIn("modifiers", self.app.detail)

    def test_empty_recognition_keeps_audio_available_to_retry(self):
        import numpy as np

        def run(session, *args, **kwargs):
            session.audio_queue.put(np.ones(16000, dtype=np.float32), 16000)
            session.request_release()
            return "", 1.0

        with patch.object(DictationSession, "run", run):
            self.app.start_recording()
            self.wait_idle()
        self.assertIsNotNone(self.app._failed_audio)
        self.assertIn("Retry", self.app.detail)
        self.app.injector.inject.assert_not_called()

    def test_cancel_invalidates_readiness_after_worker_is_interrupted(self):
        self.app.cancel_current()
        self.assertFalse(self.app._ready)

    def test_quit_cancels_pending_insertion(self):
        entered = threading.Event()
        finish = threading.Event()

        def run(session, *args, **kwargs):
            entered.set()
            finish.wait(2)
            return "must not paste", 1.0

        with patch.object(DictationSession, "run", run):
            self.app.start_recording()
            self.assertTrue(entered.wait(2))
            self.app.quit()
            finish.set()
            self.app._executor.shutdown(wait=True)
        self.app.injector.inject.assert_not_called()

    def test_incomplete_audio_never_reaches_clipboard_or_history(self):
        with patch.object(DictationSession, "run", side_effect=IncompleteRecording("queue overflow")):
            self.app.start_recording()
            self.wait_idle()
        self.app.injector.inject.assert_not_called()
        self.assertEqual(self.app.history.last(), "")
        self.assertIn("queue overflow", self.app.last_error)

    def test_retry_can_be_cancelled_without_saving_incomplete_text(self):
        import numpy as np

        self.app._failed_audio = ((np.ones(1600, dtype=np.float32), 16000),)
        entered = threading.Event()
        finish = threading.Event()

        def replay(session, *args, **kwargs):
            entered.set()
            self.assertTrue(finish.wait(2))
            return "must not be saved", 0.1

        with patch.object(DictationSession, "run", replay):
            self.app.retry_failed()
            self.assertIsNotNone(self.app._session)
            self.assertTrue(entered.wait(2))
            self.app.cancel_current()
            finish.set()
            self.wait_idle()

        self.assertEqual(self.app.history.last(), "")
        self.assertEqual(self.app.latest_text, "")
        self.assertIsNone(self.app._session)

    def test_stale_worker_cannot_override_new_status(self):
        self.app._current_id = 3
        self.app.status = "recording"
        self.app.set_status("ready", session_id=2)
        self.app._complete_work(2)
        self.assertEqual(self.app.status, "recording")

    def test_sound_cues_ignore_disabled_cancelled_and_stale_sessions(self):
        self.app._current_id = 3
        session = DictationSession(3)
        self.app._recording_cue("start", session, self.app.settings)
        self.app.sounds.play.assert_called_once_with("start")
        self.app.sounds.play.reset_mock()
        self.app._recording_cue("stop", session, replace(self.app.settings, sound_feedback=False))
        self.app._recording_cue("start", DictationSession(2), self.app.settings)
        session.cancel.set()
        self.app._recording_cue("stop", session, self.app.settings)
        self.app.sounds.play.assert_not_called()

    def test_reminder_audio_is_deferred_during_dictation_and_stopped_before_capture(self):
        self.app.recorder.is_recording = False
        self.assertTrue(self.app._play_reminder_sound())
        self.app.sounds.play.assert_called_once_with("reminder")
        self.app.sounds.play.reset_mock()
        self.app._session = DictationSession(1)
        self.assertFalse(self.app._play_reminder_sound())
        self.app.sounds.play.assert_not_called()
        self.app._session = None
        with patch.object(DictationSession, "run", return_value=("", 0)):
            self.app.start_recording()
            self.wait_idle()
        self.app.sounds.stop.assert_called_once()

    def test_nemotron_device_change_reloads_and_warms_the_backend(self):
        self.app.settings = replace(self.app.settings, backend="nemotron", nemotron_device="vulkan")
        self.app.update_settings(replace(self.app.settings, nemotron_device="cpu", language="auto"))
        self.wait_idle()
        self.backend.close.assert_called_once()
        self.backend.preload.assert_called_once()
        self.assertEqual(self.app.settings.backend, "nemotron")
        self.assertEqual(self.app.settings.nemotron_device, "cpu")
        self.assertEqual(self.app.settings.language, "en")
