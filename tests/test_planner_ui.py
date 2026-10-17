from __future__ import annotations

import ctypes
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import MagicMock, patch

from voiceprompt.planner import PlannerService
from voiceprompt.planner_ui import PlannerUI


class PlannerUITests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
            self.root.withdraw()
        except tk.TclError as exc:
            self.skipTest(f"Tk unavailable: {exc}")
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.service = PlannerService(Path(directory.name) / "planner.sqlite3")
        self.sounds = MagicMock()
        self.busy = False
        self.ui = PlannerUI(self.root, self.service, self.sounds, lambda: self.busy)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.ui.close()
        self.root.update_idletasks()
        self.root.destroy()
        self.service.close()

    def notify(self, title="DSA finished"):
        with self.service.store.transaction():
            self.service._notify(title, title, "Session finished")

    def test_tabs_and_controls_support_ninety_minutes_and_reopen_single_window(self):
        self.ui.open()
        self.root.update_idletasks()
        self.assertEqual([self.ui.notebook.tab(t, "text") for t in self.ui.notebook.tabs()], ["Tasks", "Timer", "Alarms", "Contests"])
        self.assertLess(self.ui.window.winfo_reqheight(), self.root.winfo_screenheight())
        self.ui._preset(90)
        self.assertEqual((self.ui.hours.get(), self.ui.minutes.get()), ("1", "30"))
        self.assertEqual(self.ui.timer_display["text"], "01:30:00")
        self.ui._start_timer()
        self.assertEqual(self.service.snapshot()["timer"]["work"], 5400)
        previous = self.ui.window
        self.ui._hide()
        self.ui.open()
        self.assertIs(self.ui.window, previous)

    def test_task_save_to_timer_and_alarm_dialogs_use_same_tcl_interpreter(self):
        self.ui.open()
        self.ui.task_title.set("Learn DSA")
        self.ui._quick_task()
        self.ui._render(self.service.snapshot())
        task = self.ui.tasks.get_children()[0]
        self.ui.tasks.selection_set(task)
        self.ui._timer_from_task()
        self.assertEqual(self.ui.timer_title.get(), "Learn DSA")
        self.ui._task_editor(task)
        self.ui._alarm_editor()
        self.ui._preferences_editor()
        self.ui._credentials_editor()
        self.root.update_idletasks()
        for dialog in self.ui.window.winfo_children():
            if isinstance(dialog, tk.Toplevel):
                self.assertIs(dialog.tk, self.root.tk)
                self.assertLess(dialog.winfo_reqheight(), self.root.winfo_screenheight())

    @patch("voiceprompt.planner_ui.show_without_activation")
    def test_notifications_defer_card_and_sound_until_dictation_finishes(self, show):
        self.notify()
        self.busy = True
        self.ui._reminders(self.service.snapshot())
        self.assertIsNone(self.ui.card)
        self.sounds.play.assert_not_called()
        self.busy = False
        self.ui._reminders(self.service.snapshot())
        self.assertIsNotNone(self.ui.card)
        self.sounds.play.assert_called_once_with("reminder")
        show.assert_called_once()

    @patch("voiceprompt.planner_ui.show_without_activation")
    def test_simultaneous_reminders_share_chimes_and_stop_after_three(self, show):
        self.notify("One")
        self.notify("Two")
        with patch("voiceprompt.planner_ui.time.monotonic", return_value=0) as clock:
            self.ui._reminders(self.service.snapshot())
            clock.return_value = 10
            self.ui._reminders(self.service.snapshot())
            clock.return_value = 20
            self.ui._reminders(self.service.snapshot())
            clock.return_value = 40
            self.ui._reminders(self.service.snapshot())
        self.assertEqual(self.sounds.play.call_count, 3)

    @patch("voiceprompt.planner_ui.show_without_activation")
    def test_disabled_reminder_sound_and_acknowledgment_clear_card(self, show):
        self.service.update_preferences(reminder_sound=False)
        self.notify()
        self.ui._reminders(self.service.snapshot())
        self.sounds.play.assert_not_called()
        self.service.acknowledge(self.service.snapshot()["notifications"][0]["id"])
        self.ui._reminders(self.service.snapshot())
        self.assertIsNone(self.ui.card)

    def test_pending_reminders_inbox_lists_due_and_snoozed_items(self):
        self.ui.open()
        self.notify("One")
        self.notify("Two")
        self.service.acknowledge("Two", True)
        self.ui._open_inbox()
        def visit(widget):
            yield widget
            for child in widget.winfo_children():
                yield from visit(child)
        tree = next(w for w in visit(self.ui._inbox) if isinstance(w, ttk.Treeview))
        self.assertEqual(len(tree.get_children()), 2)
        self.root.update()
        for button in (w for w in visit(self.ui._inbox) if isinstance(w, ttk.Button)):
            self.assertTrue(button.winfo_ismapped(), button["text"])
        tree.selection_set("One")
        tree.focus("One")
        self.ui._rows(tree, [("One", ("One", "Session finished", "now")), ("Two", ("Two", "Session finished", "later"))])
        self.assertEqual(tree.focus(), "One")

    def test_navigation_and_primary_controls_fit_at_100_125_and_150_percent(self):
        from voiceprompt.theme import pixels
        for scale in (1.0, 1.25, 1.5):
            with self.subTest(scale=scale):
                root = tk.Tk()
                root.withdraw()
                root.tk.call("tk", "scaling", scale * 96 / 72)
                ui = PlannerUI(root, self.service, MagicMock(), lambda: False)
                try:
                    ui.open()
                    # Check the narrow supported layout, rather than a forgiving wide window.
                    ui.window.geometry(f"{pixels(root, 800)}x{min(pixels(root, 560), root.winfo_screenheight() - 90)}")
                    for name in ui.pages:
                        ui._navigate(name)
                        root.update()
                        self.assertIn(name, ui.nav_buttons)
                        self.assertEqual(ui.nav_buttons[name]["style"], "SelectedNav.TButton")
                        def visit(widget):
                            yield widget
                            for child in widget.winfo_children():
                                yield from visit(child)
                        for widget in visit(ui.pages[name]):
                            if isinstance(widget, ttk.Button):
                                self.assertTrue(widget.winfo_ismapped(), widget["text"])
                                self.assertGreaterEqual(widget.winfo_width(), widget.winfo_reqwidth() - 2, widget["text"])
                                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), ui.window.winfo_rootx() + ui.window.winfo_width() + 2, widget["text"])
                    self.assertLessEqual(ui.window.winfo_height(), root.winfo_screenheight())
                finally:
                    ui.close()
                    root.update_idletasks()
                    root.destroy()

    def test_timer_controls_and_optional_pomodoro_match_session_state(self):
        self.ui.open()
        self.assertIn("disabled", self.ui.timer_controls["pause"].state())
        self.ui.pomodoro.set(True)
        self.ui._toggle_pomodoro()
        self.root.update_idletasks()
        self.assertEqual(self.ui.pomodoro_options.winfo_manager(), "pack")
        self.ui._start_timer()
        self.ui._render(self.service.snapshot())
        self.assertNotIn("disabled", self.ui.timer_controls["pause"].state())
        self.assertIn("disabled", self.ui.timer_controls["resume"].state())
        self.service.timer_action("pause")
        self.ui._render(self.service.snapshot())
        self.assertNotIn("disabled", self.ui.timer_controls["resume"].state())

    def test_hidden_pomodoro_settings_do_not_block_a_countdown(self):
        self.ui.open()
        self.ui.short_break.set("invalid")
        self.ui.rounds.set("invalid")
        self.ui._preset(90)
        self.ui._start_timer()
        self.assertEqual(self.service.snapshot()["timer"]["work"], 5400)

    def test_keyboard_focus_reveals_controls_in_a_scrolled_form(self):
        from types import SimpleNamespace
        from voiceprompt.theme import ScrollablePage
        self.ui.open()
        self.ui._navigate("Timer")
        scroller = next(w for w in self.ui.pages["Timer"].winfo_children() if isinstance(w, ScrollablePage))
        self.ui.window.minsize(400, 300)
        self.ui.window.geometry("1000x400")
        self.root.update()
        target = self.ui.timer_controls["cancel"]
        scroller._reveal_focus(SimpleNamespace(widget=target))
        self.root.update()
        self.assertGreater(scroller.canvas.yview()[0], 0)
        self.assertLessEqual(target.winfo_rooty() + target.winfo_height(), scroller.canvas.winfo_rooty() + scroller.canvas.winfo_height())

    @unittest.skipUnless(sys.platform == "win32", "Windows notification behavior")
    def test_real_reminder_window_is_visible_without_changing_foreground(self):
        user32 = ctypes.WinDLL("user32")
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        # Observe the user's current foreground; the test never activates another app.
        before = user32.GetForegroundWindow()
        self.notify()
        self.ui._reminders(self.service.snapshot())
        self.root.update()
        self.assertEqual(user32.GetForegroundWindow(), before)
        from ctypes import wintypes
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        handle = user32.GetParent(self.ui.card.winfo_id()) or self.ui.card.winfo_id()
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.assertTrue(user32.IsWindowVisible(handle))
        self.assertTrue(user32.IsWindowVisible(self.ui.card.winfo_id()), "Reminder content must be mapped as well as its wrapper")
        for child in self.ui.card.winfo_children():
            self.assertTrue(user32.IsWindowVisible(child.winfo_id()), "Reminder controls must be visible")
