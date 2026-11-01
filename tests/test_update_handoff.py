import io
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from voiceprompt.desktop_protocol import Writer
from voiceprompt.desktop_sidecar import DesktopService
from voiceprompt.main import VoicePromptApp


class UpdateHandoffTests(unittest.TestCase):
    def controller(self):
        return SimpleNamespace(_control=threading.RLock(), _updating=False,
                               _quitting=False, _working=False, _session=None,
                               recorder=SimpleNamespace(is_recording=False),
                               _failed_audio=None, insertion_status="none", _pending_settings=None)

    def test_preparation_rejects_every_state_that_could_lose_work(self):
        for name, value in [("_working", True), ("_quitting", True), ("_session", object()),
                            ("_failed_audio", b"recording"), ("insertion_status", "pending"),
                            ("_pending_settings", object())]:
            with self.subTest(state=name):
                controller = self.controller()
                setattr(controller, name, value)
                with self.assertRaises(ValueError): VoicePromptApp.prepare_update(controller)
                self.assertFalse(controller._updating)
        controller = self.controller()
        controller.recorder.is_recording = True
        with self.assertRaises(ValueError): VoicePromptApp.prepare_update(controller)

    def test_quiesced_controller_ignores_new_hotkey_and_model_work(self):
        controller = self.controller()
        controller._begin_work = Mock(side_effect=AssertionError("work must remain blocked"))
        VoicePromptApp.prepare_update(controller)
        self.assertTrue(controller._updating)
        VoicePromptApp.start_recording(controller)
        VoicePromptApp.preload_model(controller)
        VoicePromptApp.check_microphone(controller)
        VoicePromptApp.retry_last(controller)
        VoicePromptApp.cancel_update(controller)
        self.assertFalse(controller._updating)

    def test_sidecar_blocks_mutations_during_handoff(self):
        controller = self.controller()
        controller.pill = SimpleNamespace(on_navigation=None)
        controller.prepare_update = lambda: VoicePromptApp.prepare_update(controller)
        controller.cancel_update = lambda: VoicePromptApp.cancel_update(controller)
        service = DesktopService(controller, Writer(io.BytesIO()))
        self.assertEqual(service.dispatch("update.prepare", {}), {"ok": True})
        for method in ("record.start", "settings.save", "planner.task.save"):
            with self.assertRaisesRegex(ValueError, "closing"):
                service.dispatch(method, {})
        self.assertEqual(service.dispatch("update.cancel", {}), {"ok": True})
        self.assertFalse(controller._updating)
