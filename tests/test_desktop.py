import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox
from voiceprompt.desktop import DesktopHost, PAGES
from desktop_helpers import make_controller


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.controller = make_controller(self.directory.name)
        self.adapter = type("Adapter", (), {"events": __import__("queue").SimpleQueue()})()
        with patch("voiceprompt.desktop.microphones", return_value=["Test microphone"]):
            self.host = DesktopHost(self.controller, self.adapter)
        self.window = self.host.window
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.host.stop()
        self.controller.planner.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def test_all_pages_exist_and_everyday_controls_precede_advanced(self):
        self.assertEqual(self.window.stack.count(), 7)
        for page in PAGES:
            self.window.show_page(page)
            self.app.processEvents()
            self.assertEqual(self.window.navigation.currentItem().text(), page)
        self.assertFalse(self.window.advanced.isVisible())
        self.window.advanced_toggle.click()
        self.assertTrue(self.window.advanced.isVisible())

    def test_tasks_and_ninety_minute_timer_use_existing_services(self):
        self.window.quick_task.setText("Study DSA")
        self.window.add_quick_task()
        self.window.refresh(force=True)
        self.window.tables["Tasks"].selectRow(0)
        self.window.timer_for_task()
        self.window.set_duration(90)
        self.window.start_timer()
        timer = self.controller.planner.snapshot()["timer"]
        self.assertEqual(timer["title"], "Study DSA")
        self.assertEqual(timer["work"], 5400)
        self.assertIsNotNone(timer["task_id"])

    def test_settings_preserve_engine_and_save_dictionary(self):
        self.window.fields["backend"].setCurrentText("nemotron")
        self.window.fields["nemotron_device"].setCurrentText("cpu")
        self.window.fields["sound_feedback"].setChecked(False)
        self.window.dictionary.setPlainText("my project=MyProject")
        self.window.save_preferences()
        self.assertEqual(self.controller.settings.backend, "nemotron")
        self.assertEqual(self.controller.settings.nemotron_device, "cpu")
        self.assertEqual(self.controller.settings.replacements, {"my project": "MyProject"})
        self.assertFalse(self.controller.settings.sound_feedback)

    def test_visible_error_and_recovery_do_not_disappear_as_ready(self):
        self.controller.status = "error"
        self.controller.last_error = "Recognition took too long. Retry your recording."
        self.controller._failed_audio = ((b"audio", 16000),)
        self.window.refresh(force=True)
        self.assertEqual(self.window.status_title.text(), "Needs attention")
        self.assertIn("Retry", self.window.status_detail.text())
        self.assertTrue(self.window.recovery.isVisible())

    def test_onboarding_and_copy_actions(self):
        self.controller.settings.onboarding_completed = False
        self.window.refresh(force=True)
        self.assertTrue(self.window.onboarding.isVisible())
        self.window.complete_setup()
        self.window.refresh(force=True)
        self.assertFalse(self.window.onboarding.isVisible())
        self.window.copy_text("hello world")
        self.assertEqual(self.app.clipboard().text(), "hello world")

    def test_transcript_history_survives_app_window_recreation(self):
        self.controller.history.add("test words", 2, "whisper")
        self.window.refresh(force=True)
        self.assertEqual(self.window.tables["History"].rowCount(), 1)
        self.assertEqual(self.window.tables["History"].item(0, 1).text(), "test words")

    def test_pages_fit_minimum_window_width_without_horizontal_scrolling(self):
        self.window.resize(800, 560)
        for page in PAGES:
            with self.subTest(page=page):
                self.window.show_page(page)
                self.app.processEvents()
                scroll = self.window.stack.currentWidget()
                self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
