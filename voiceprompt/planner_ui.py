from __future__ import annotations

import ctypes
import math
import logging
import sys
import time
import tkinter as tk
import webbrowser
from datetime import datetime, timedelta
from tkinter import messagebox, ttk
from zoneinfo import ZoneInfo

from voiceprompt.contests import PLATFORMS, safe_contest_url
from voiceprompt.planner import PlannerService, local_timestamp
from voiceprompt.theme import (ACCENT, BACKGROUND, INK, LINE, MUTED, RAIL, SURFACE,
                               ScrollablePage, fit_window, install_theme, pixels)


def format_duration(seconds: float) -> str:
    seconds = max(0, math.ceil(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def show_without_activation(window: tk.Toplevel) -> None:
    """A reminder must not become the destination of a pending dictation paste."""
    window.update_idletasks()
    if sys.platform == "win32":
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        handle = user32.GetParent(window.winfo_id()) or window.winfo_id()
        get_style = user32.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.GetWindowLongW
        set_style = user32.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetWindowLongW
        get_style.argtypes = [wintypes.HWND, ctypes.c_int]
        get_style.restype = ctypes.c_ssize_t
        set_style.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        set_style.restype = ctypes.c_ssize_t
        set_style(handle, -20, get_style(handle, -20) | 0x08000000 | 0x80)  # NOACTIVATE, TOOLWINDOW
        window.deiconify()
        window.update_idletasks()
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        user32.SetWindowPos.restype = wintypes.BOOL
        # NOACTIVATE is installed before Tk maps its child controls.
        user32.SetWindowPos(handle, -1, 0, 0, 0, 0, 0x0010 | 0x0001 | 0x0002 | 0x0040)
    else:
        window.deiconify()


class PlannerUI:
    """All Tk windows and updates stay on the floating pill's main thread."""

    def __init__(self, root: tk.Tk, service: PlannerService, sounds, audio_busy, on_reminder_sound=None):
        install_theme(root)
        self.root, self.service, self.sounds, self.audio_busy = root, service, sounds, audio_busy
        self.on_reminder_sound = on_reminder_sound
        self.window = None
        self.card = None
        self._card_ids = ()
        self._sound_state = {}
        self._last_view = None
        self._inbox = None
        self._stopped = False
        self._after = root.after(500, self._poll)

    def close(self):
        self._stopped = True
        self.root.after_cancel(self._after)
        if self.card:
            self.card.destroy()
        if self.window:
            self.window.destroy()

    def open(self):
        if self.window and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            return
        self.window = tk.Toplevel(self.root)
        self.window.title("VoicePrompt Planner")
        fit_window(self.window)
        self.window.protocol("WM_DELETE_WINDOW", self._hide)
        p = lambda value: pixels(self.root, value)
        shell = ttk.Frame(self.window)
        shell.pack(fill="both", expand=True)
        rail = ttk.Frame(shell, style="Rail.TFrame", padding=(p(20), p(28)), width=p(200))
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        ttk.Label(rail, text="VoicePrompt", style="RailTitle.TLabel").pack(anchor="w")
        ttk.Label(rail, text="A little more focus.", style="RailMuted.TLabel").pack(anchor="w", pady=(p(5), p(34)))
        self.nav_buttons = {}
        for key, label in (("Tasks", "Tasks"), ("Timer", "Focus timer"), ("Alarms", "Alarms"), ("Contests", "Contests")):
            button = ttk.Button(rail, text=label, style="Nav.TButton", command=lambda name=key: self._navigate(name))
            button.pack(fill="x", pady=p(3))
            self.nav_buttons[key] = button
        bottom = ttk.Frame(rail, style="Rail.TFrame")
        bottom.pack(side="bottom", fill="x")
        ttk.Separator(bottom).pack(fill="x", pady=p(14))
        ttk.Label(bottom, text="Reminders stay on\nwhile in the tray.", style="RailMuted.TLabel", justify="left").pack(anchor="w")
        self.session_hint = ttk.Label(bottom, text="No active session", style="RailMuted.TLabel", wraplength=p(160))
        self.session_hint.pack(anchor="w", pady=(p(16), 0))
        frame = ttk.Frame(shell, padding=(p(32), p(24), p(28), p(14)))
        frame.pack(side="left", fill="both", expand=True)
        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, p(22)))
        title_area = ttk.Frame(top)
        title_area.pack(side="left", fill="x", expand=True)
        self.section_title = ttk.Label(title_area, text="Your tasks", style="Title.TLabel")
        self.section_title.pack(anchor="w")
        self.section_description = ttk.Label(title_area, text="", style="Muted.TLabel")
        self.section_description.pack(anchor="w", pady=(p(5), 0))
        self.inbox_button = ttk.Button(top, text="Reminders", command=self._guard(self._open_inbox))
        self.inbox_button.pack(side="right", anchor="n", pady=p(4))
        self.notebook = ttk.Notebook(frame, style="Workspace.TNotebook")
        self.notebook.pack(fill="both", expand=True)
        self.pages = {}
        for title in ("Tasks", "Timer", "Alarms", "Contests"):
            page = ttk.Frame(self.notebook)
            self.notebook.add(page, text=title)
            self.pages[title] = page
        self.notebook.bind("<<NotebookTabChanged>>", lambda _: self._navigation_changed())
        self._tasks_page()
        self._timer_page()
        self._alarms_page()
        self._contests_page()
        self.footer = ttk.Label(frame, text="", style="Muted.TLabel", font=("Segoe UI", 9))
        self.footer.pack(anchor="w", pady=(p(14), 0))
        self._navigation_changed()
        self._last_view = None
        self._render(self.service.snapshot())

    def _navigate(self, page):
        self.notebook.select(self.pages[page])
        self._navigation_changed()

    def _navigation_changed(self):
        selected = self.notebook.tab(self.notebook.select(), "text")
        copy = {
            "Tasks": ("Your tasks", "Capture a task. Give it some focused time."),
            "Timer": ("Time to focus", "Your activity, your pace, your session length."),
            "Alarms": ("A timely reminder", "Set it once, or make it part of your routine."),
            "Contests": ("Your next challenge", "Upcoming programming contests, in your local time."),
        }
        title, description = copy[selected]
        self.section_title.configure(text=title)
        self.section_description.configure(text=description)
        for name, button in self.nav_buttons.items():
            button.configure(style="SelectedNav.TButton" if name == selected else "Nav.TButton")

    def _hide(self):
        self.window.withdraw()

    def _guard(self, fn):
        def run():
            try:
                fn()
                self._last_view = None
                self._render(self.service.snapshot())
            except Exception as exc:
                # Only known, user-facing errors may include a provider message.
                from voiceprompt.contests import ContestFetchError
                message = str(exc) if isinstance(exc, (ValueError, ContestFetchError, KeyError)) else "That action could not be completed. Please try again."
                messagebox.showerror("VoicePrompt Planner", message, parent=self.window)
        return run

    def _button(self, parent, title, fn, style="TButton"):
        button = ttk.Button(parent, text=title, command=self._guard(fn), style=style)
        button.pack(side="left", padx=(0, pixels(self.root, 8)), pady=pixels(self.root, 4))
        return button

    def _tree(self, page, columns):
        holder = ttk.Frame(page)
        holder.pack(fill="both", expand=True, pady=(pixels(self.root, 16), pixels(self.root, 14)))
        tree = ttk.Treeview(holder, columns=[c[0] for c in columns], show="headings", selectmode="browse", height=7)
        for name, label, width in columns:
            tree.heading(name, text=label)
            tree.column(name, width=pixels(self.root, width), minwidth=pixels(self.root, 60), anchor="w")
        scroll = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        tree.tag_configure("alternate", background="#F7FAF6")
        tree.tag_configure("completed", foreground=MUTED)
        return tree

    @staticmethod
    def _selected(tree):
        chosen = tree.selection()
        if not chosen:
            raise ValueError("Select an item first.")
        return chosen[0]

    def _entry(self, parent, label, initial="", width=30):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=pixels(self.root, 6))
        ttk.Label(row, text=label, width=23).pack(side="left")
        variable = tk.StringVar(master=self.root, value=initial)
        ttk.Entry(row, textvariable=variable, width=width).pack(side="left", fill="x", expand=True)
        return variable

    def _tasks_page(self):
        page = self.pages["Tasks"]
        bar = ttk.Frame(page)
        bar.pack(fill="x")
        self.task_title = tk.StringVar(master=self.root)
        task_entry = ttk.Entry(bar, textvariable=self.task_title)
        task_entry.pack(side="left", fill="x", expand=True, padx=(0, pixels(self.root, 10)), ipady=pixels(self.root, 3))
        task_entry.bind("<Return>", lambda _: self._guard(self._quick_task)())
        self._button(bar, "Add task", self._quick_task, "Primary.TButton")
        self._button(bar, "More details…", lambda: self._task_editor())
        ttk.Label(page, text="Type a task above and press Enter to add it.", style="Muted.TLabel", font=("Segoe UI", 10)).pack(anchor="w", pady=(pixels(self.root, 7), 0))
        self.tasks = self._tree(page, [("state", "Status", 80), ("title", "Task", 400), ("due", "Reminder", 180)])
        self.tasks.bind("<Double-1>", lambda _: self._guard(lambda: self._task_editor(self._selected(self.tasks)))())
        self.task_empty = ttk.Label(self.tasks, text="A clear list, a fresh start.\nAdd your first task above.",
                                    style="SurfaceMuted.TLabel", justify="center", anchor="center")
        bar = ttk.Frame(page)
        bar.pack(fill="x")
        self._button(bar, "Complete / reopen", lambda: self.service.complete_task(self._selected(self.tasks)))
        self._button(bar, "Edit…", lambda: self._task_editor(self._selected(self.tasks)))
        self._button(bar, "Start a timer", self._timer_from_task)
        self._button(bar, "Delete", lambda: self._delete("task", self.tasks), "Danger.TButton")
        bar.pack_configure(side="bottom", before=self.tasks.master)

    def _quick_task(self):
        self.service.save_task(self.task_title.get())
        self.task_title.set("")

    def _delete(self, kind, tree):
        item_id = self._selected(tree)
        if messagebox.askyesno("Delete item", "Delete this item and its pending reminders?", parent=self.window):
            self.service.delete(kind, item_id)

    def _editor(self, title):
        dialog = tk.Toplevel(self.window)
        dialog.title(title)
        dialog.transient(self.window)
        dialog.resizable(True, True)
        frame = ttk.Frame(dialog, padding=pixels(self.root, 24))
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=title, style="Heading.TLabel").pack(anchor="w", pady=(0, pixels(self.root, 16)))
        dialog.bind("<Escape>", lambda _: dialog.destroy())
        def fit():
            if dialog.winfo_exists() and dialog is not self._inbox:
                margin = pixels(self.root, 40)
                dialog.geometry(f"{min(dialog.winfo_reqwidth(), dialog.winfo_screenwidth() - margin)}x"
                                f"{min(dialog.winfo_reqheight(), dialog.winfo_screenheight() - margin)}")
        dialog.after_idle(fit)
        return dialog, frame

    def _task_editor(self, item_id=None):
        item = self.service.store.get("task", item_id or "") or {}
        dialog, frame = self._editor("Task details")
        title = self._entry(frame, "Task", item.get("title", ""))
        notes = self._entry(frame, "Notes", item.get("notes", ""))
        due = self._entry(frame, "Remind at (optional)", self._date(item.get("due")))
        ttk.Label(frame, text="YYYY-MM-DD HH:MM · " + self.service.preferences()["timezone"]).pack(anchor="w", pady=8)
        def save():
            timestamp = local_timestamp(due.get(), self.service.preferences()["timezone"]) if due.get().strip() else None
            self.service.save_task(title.get(), notes.get(), timestamp, item_id)
            dialog.destroy()
        self._button(frame, "Save task", save, "Primary.TButton")

    def _timer_page(self):
        scroller = ScrollablePage(self.pages["Timer"])
        scroller.pack(fill="both", expand=True)
        page = scroller.body
        p = lambda value: pixels(self.root, value)
        stage = ttk.Frame(page, style="Surface.TFrame", padding=(p(24), p(18)))
        stage.pack(fill="x", pady=(0, p(20)))
        self.timer_display = ttk.Label(stage, text="00:25:00", style="Timer.TLabel", anchor="center")
        self.timer_display.pack(fill="x")
        self.timer_status = ttk.Label(stage, text="Ready when you are", style="SurfaceMuted.TLabel", anchor="center")
        self.timer_status.pack(fill="x", pady=(0, p(16)))
        self.timer_progress = ttk.Progressbar(stage, orient="horizontal", mode="determinate", maximum=100)
        self.timer_progress.pack(fill="x")
        self.timer_title = self._entry(page, "Activity", "Learn DSA")
        self._timer_task_id = None
        self.hours = tk.StringVar(master=self.root, value="0")
        self.minutes = tk.StringVar(master=self.root, value="25")
        row = ttk.Frame(page)
        row.pack(fill="x", pady=5)
        ttk.Label(row, text="Session length", width=23).pack(side="left")
        ttk.Spinbox(row, from_=0, to=9999, textvariable=self.hours, width=6).pack(side="left")
        ttk.Label(row, text=" hours   ").pack(side="left")
        ttk.Spinbox(row, from_=0, to=59, textvariable=self.minutes, width=6).pack(side="left")
        ttk.Label(row, text=" minutes").pack(side="left")
        row = ttk.Frame(page)
        row.pack(fill="x", pady=5)
        for minutes in (20, 25, 30, 45, 60, 90, 120):
            self._button(row, f"{minutes}m", lambda m=minutes: self._preset(m))
        self.pomodoro = tk.BooleanVar(master=self.root, value=False)
        ttk.Separator(page).pack(fill="x", pady=p(12))
        ttk.Checkbutton(page, text="Add Pomodoro work and break cycles", variable=self.pomodoro,
                        command=self._toggle_pomodoro).pack(anchor="w", pady=p(4))
        row = ttk.Frame(page)
        self.pomodoro_options = row
        self.short_break = tk.StringVar(master=self.root, value="5")
        self.long_break = tk.StringVar(master=self.root, value="15")
        self.rounds = tk.StringVar(master=self.root, value="4")
        for label, variable in (("Short break (min)", self.short_break), ("Long break (min)", self.long_break), ("Rounds", self.rounds)):
            field = ttk.Frame(row)
            field.pack(side="left", padx=(0, pixels(self.root, 20)))
            ttk.Label(field, text=label).pack(anchor="w", pady=(0, pixels(self.root, 6)))
            ttk.Spinbox(field, from_=1, to=100, textvariable=variable, width=6).pack(anchor="w")
        row = ttk.Frame(page)
        self.timer_actions = row
        row.pack(fill="x", pady=(p(16), p(8)))
        self._button(row, "Start session", self._start_timer, "Primary.TButton")
        self.timer_controls = {}
        for action in ("pause", "resume", "restart", "cancel"):
            self.timer_controls[action] = self._button(row, action.capitalize(), lambda a=action: self.service.timer_action(a))
        ttk.Label(page, text="Choose any duration. Your timer keeps its place when this window closes.",
                  style="Muted.TLabel", wraplength=p(540)).pack(anchor="w", pady=p(8))
        self.hours.trace_add("write", lambda *_: self._update_timer_preview())
        self.minutes.trace_add("write", lambda *_: self._update_timer_preview())

    def _update_timer_preview(self):
        if self.service.store.get("timer", "active") is None:
            try:
                self.timer_display.configure(text=format_duration(int(self.hours.get()) * 3600 + int(self.minutes.get()) * 60))
            except ValueError:
                pass

    def _toggle_pomodoro(self):
        if self.pomodoro.get():
            self.pomodoro_options.pack(fill="x", pady=pixels(self.root, 8), before=self.timer_actions)
        else:
            self.pomodoro_options.pack_forget()

    def _preset(self, minutes):
        self.hours.set(str(minutes // 60))
        self.minutes.set(str(minutes % 60))

    def _start_timer(self):
        hours, minutes = int(self.hours.get()), int(self.minutes.get())
        if hours < 0 or not 0 <= minutes <= 59:
            raise ValueError("Use nonnegative hours and minutes from 0–59.")
        timer = self.service.snapshot()["timer"]
        replacing = bool(timer and timer["status"] in {"paused", "running"})
        if replacing and not messagebox.askyesno("Replace timer", "Replace the active timer with this session?", parent=self.window):
            return
        pomodoro = self.pomodoro.get()
        self.service.start_timer(self.timer_title.get(), hours * 3600 + minutes * 60,
                                 mode="pomodoro" if self.pomodoro.get() else "countdown",
                                 short_break=float(self.short_break.get()) * 60 if pomodoro else 300,
                                 long_break=float(self.long_break.get()) * 60 if pomodoro else 900,
                                 rounds=int(self.rounds.get()) if pomodoro else 4, task_id=self._timer_task_id, replace=replacing)

    def _timer_from_task(self):
        item_id = self._selected(self.tasks)
        task = self.service.store.get("task", item_id)
        self._timer_task_id = item_id
        self.timer_title.set(task["title"])
        self.notebook.select(self.pages["Timer"])

    def _alarms_page(self):
        page = self.pages["Alarms"]
        row = ttk.Frame(page)
        row.pack(fill="x")
        self._button(row, "Add alarm…", lambda: self._alarm_editor(), "Primary.TButton")
        ttk.Label(row, text="Once, daily, or on your chosen weekdays.", style="Muted.TLabel").pack(side="left", padx=pixels(self.root, 12))
        self.alarms = self._tree(page, [("state", "Status", 90), ("title", "Alarm", 300), ("due", "Next occurrence", 180), ("repeat", "Repeats", 180)])
        self.alarm_empty = ttk.Label(self.alarms, text="Nothing to remember just yet.\nAdd an alarm for your next important moment.",
                                     style="SurfaceMuted.TLabel", justify="center", anchor="center")
        row = ttk.Frame(page)
        row.pack(fill="x")
        self._button(row, "Edit…", lambda: self._alarm_editor(self._selected(self.alarms)))
        self._button(row, "Enable / disable", lambda: self.service.toggle_alarm(self._selected(self.alarms)))
        self._button(row, "Delete", lambda: self._delete("alarm", self.alarms), "Danger.TButton")
        row.pack_configure(side="bottom", before=self.alarms.master)

    def _alarm_editor(self, item_id=None):
        item = self.service.store.get("alarm", item_id or "") or {}
        dialog, frame = self._editor("Alarm")
        title = self._entry(frame, "Alarm name", item.get("title", ""))
        initial = item.get("due") or self.service.now() + 3600
        due = self._entry(frame, "First date and time", self._date(initial))
        ttk.Label(frame, text="YYYY-MM-DD HH:MM · " + self.service.preferences()["timezone"]).pack(anchor="w", pady=6)
        ttk.Label(frame, text="Repeat on (leave all unchecked for a one-time alarm)").pack(anchor="w", pady=6)
        row = ttk.Frame(frame)
        row.pack(fill="x")
        weekdays = []
        for day, label in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            variable = tk.BooleanVar(master=self.root, value=day in item.get("weekdays", []))
            weekdays.append(variable)
            ttk.Checkbutton(row, text=label, variable=variable).pack(side="left")
        def save():
            self.service.save_alarm(title.get(), local_timestamp(due.get(), self.service.preferences()["timezone"]),
                                    [i for i, variable in enumerate(weekdays) if variable.get()], item_id)
            dialog.destroy()
        self._button(frame, "Save alarm", save, "Primary.TButton")

    def _contests_page(self):
        page = self.pages["Contests"]
        prefs = self.service.preferences()
        row = ttk.Frame(page)
        row.pack(fill="x")
        self.platforms = {}
        for platform, label in PLATFORMS.items():
            variable = tk.BooleanVar(master=self.root, value=platform in prefs["platforms"])
            self.platforms[platform] = variable
            ttk.Checkbutton(row, text=label, variable=variable, command=self._guard(self._save_contest_options)).pack(side="left", padx=(0, pixels(self.root, 10)))
        self._button(row, "Refresh", lambda: self.service.refresh_contests(force=True))
        self.contests = self._tree(page, [("platform", "Platform", 100), ("name", "Contest", 350), ("start", "Starts", 160), ("muted", "Reminders", 90)])
        self.contest_empty = ttk.Label(self.contests, text="Your next challenge will appear here.\nRefresh schedules or connect your CLIST account.",
                                       style="SurfaceMuted.TLabel", justify="center", anchor="center")
        row = ttk.Frame(page)
        row.pack(fill="x")
        self._button(row, "Open contest", self._open_contest, "Primary.TButton")
        self._button(row, "Mute / unmute", lambda: self.service.mute_contest(self._selected(self.contests)))
        self._button(row, "Settings…", self._preferences_editor)
        self._button(row, "Connect CLIST…", self._credentials_editor)
        row.pack_configure(side="bottom", before=self.contests.master)
        self.source_status = ttk.Label(page, text="", wraplength=pixels(self.root, 620), justify="left", style="Muted.TLabel", font=("Segoe UI", 10))
        self.source_status.pack(fill="x", pady=pixels(self.root, 14))
        self.source_status.bind("<Configure>", lambda e: self.source_status.configure(wraplength=e.width))
        self.source_status.pack_configure(side="bottom", before=row)

    def _save_contest_options(self):
        self.service.update_preferences(platforms=[p for p, v in self.platforms.items() if v.get()])

    def _open_contest(self):
        contest = self.service.store.get("contest", self._selected(self.contests))
        if contest and safe_contest_url(contest["url"], contest["platform"]):
            webbrowser.open(contest["url"])

    def _credentials_editor(self):
        dialog, frame = self._editor("Connect CLIST")
        ttk.Label(frame, text="One CLIST key connects LeetCode, CodeChef, and AtCoder.\nCodeforces works without a key.").pack(anchor="w", pady=(0, 10))
        username = self._entry(frame, "CLIST username", self.service.preferences()["clist_username"])
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="API key", width=25).pack(side="left")
        key = tk.StringVar(master=self.root)
        ttk.Entry(row, textvariable=key, show="•", width=36).pack(side="left")
        ttk.Label(frame, text="The key is saved in Windows credential storage.\nConnection results appear under Contests after the test.").pack(anchor="w", pady=10)
        self._button(frame, "Get your CLIST key", lambda: webbrowser.open("https://clist.by/api/v4/doc/"))
        def connect():
            self.service.connect_clist(username.get(), key.get())
            key.set("")
            dialog.destroy()
        self._button(frame, "Save and test connection", connect, "Primary.TButton")

    def _preferences_editor(self):
        prefs = self.service.preferences()
        dialog, frame = self._editor("Reminder settings")
        zone = self._entry(frame, "Timezone (IANA name)", prefs["timezone"])
        minutes = self._entry(frame, "Minutes before contest", str(prefs["contest_minutes"]))
        hour = self._entry(frame, "Daily summary hour (0–23)", str(prefs["summary_hour"]))
        summary = tk.BooleanVar(master=self.root, value=prefs["daily_summary"])
        sound = tk.BooleanVar(master=self.root, value=prefs["reminder_sound"])
        ttk.Checkbutton(frame, text="Daily contest summary", variable=summary).pack(anchor="w", pady=6)
        ttk.Checkbutton(frame, text="Play gentle reminder sounds", variable=sound).pack(anchor="w", pady=6)
        def save():
            self.service.update_preferences(timezone=zone.get().strip(), contest_minutes=int(minutes.get()),
                                            summary_hour=int(hour.get()), daily_summary=summary.get(), reminder_sound=sound.get())
            dialog.destroy()
        self._button(frame, "Save settings", save, "Primary.TButton")

    def _open_inbox(self):
        if self._inbox and self._inbox.winfo_exists():
            self._inbox.lift()
            return
        dialog, frame = self._editor("Pending reminders")
        self._inbox = dialog
        fit_window(dialog, 760, 480, minimum=(600, 360))
        ttk.Label(frame, text="Pending and snoozed reminders", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tree = self._tree(frame, [("title", "Reminder", 250), ("detail", "Details", 280), ("due", "Notify at", 150)])
        row = ttk.Frame(frame)
        row.pack(fill="x")
        def action(snooze):
            self.service.acknowledge(self._selected(tree), snooze)
            refresh()
        self._button(row, "Dismiss", lambda: action(False))
        self._button(row, "Snooze 5m", lambda: action(True))
        self._button(row, "Dismiss all", lambda: dismiss_all())
        row.pack_configure(side="bottom", before=tree.master)
        def dismiss_all():
            for item_id in tree.get_children():
                self.service.acknowledge(item_id)
            refresh()
        def refresh():
            if not dialog.winfo_exists():
                return
            items = [n for n in self.service.snapshot()["notifications"] if not n["dismissed"] and
                     (not n.get("expires") or n["expires"] > self.service.now())]
            self._rows(tree, [(n["id"], (n["title"], n["detail"], self._date(n["due"]))) for n in sorted(items, key=lambda n: n["due"])])
        poll_id = None
        def poll():
            nonlocal poll_id
            if dialog.winfo_exists():
                refresh()
                poll_id = dialog.after(1000, poll)
        def stop_poll(event):
            if event.widget is dialog and poll_id is not None:
                dialog.after_cancel(poll_id)
        dialog.bind("<Destroy>", stop_poll, add="+")
        poll()

    def _date(self, timestamp):
        if timestamp is None:
            return ""
        return datetime.fromtimestamp(timestamp, ZoneInfo(self.service.preferences()["timezone"])).strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _rows(tree, rows):
        chosen = tree.selection()
        focused = tree.focus()
        position = tree.yview()
        tree.delete(*tree.get_children())
        for index, (item_id, values) in enumerate(rows):
            tags = ["alternate"] if index % 2 else []
            if values and values[0] == "Done":
                tags.append("completed")
            tree.insert("", "end", iid=item_id, values=values, tags=tags)
        if chosen and tree.exists(chosen[0]):
            tree.selection_set(chosen[0])
        if focused and tree.exists(focused):
            tree.focus(focused)
        tree.yview_moveto(position[0])

    def _render(self, data):
        if not self.window or not self.window.winfo_exists():
            return
        timer = data["timer"]
        if timer:
            self.timer_display.configure(text=format_duration(timer["remaining"]))
            self.timer_status.configure(text=f"{timer['title']} · {timer['status'].capitalize()} · {timer['phase'].replace('_', ' ')}" +
                                        (f" · {timer['completed']}/{timer['rounds']} work rounds" if timer["mode"] == "pomodoro" else ""))
            phase_duration = timer.get(timer["phase"], timer["work"])
            self.timer_progress["value"] = max(0, min(100, (1 - timer["remaining"] / phase_duration) * 100))
            self.session_hint.configure(text=f"{timer['title']}\n{format_duration(timer['remaining'])} · {timer['status']}")
        state = timer["status"] if timer else "idle"
        for action, control in self.timer_controls.items():
            available = {"pause": state == "running", "resume": state == "paused",
                         "restart": timer is not None, "cancel": state in {"running", "paused"}}[action]
            control.state(["!disabled"] if available else ["disabled"])
        count = sum(not n["dismissed"] and (not n.get("expires") or n["expires"] > self.service.now()) for n in data["notifications"])
        self.inbox_button.configure(text=f"Reminders ({count})" if count else "Reminders")
        view = (data["tasks"], data["alarms"], data["contests"], data["sources"], data["preferences"], data["syncing"])
        if view == self._last_view:
            return
        self._last_view = view
        self._rows(self.tasks, [(t["id"], ("Done" if t["done"] else "To do", t["title"], self._date(t["due"])))
                                for t in sorted(data["tasks"], key=lambda t: (t["done"], t["title"].lower()))])
        self._rows(self.alarms, [(a["id"], ("Enabled" if a["enabled"] else "Off", a["title"], self._date(a["due"]),
                                          ", ".join(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[d] for d in a["weekdays"]) or "Once"))
                                 for a in sorted(data["alarms"], key=lambda a: a["due"])])
        self._rows(self.contests, [(c["id"], (PLATFORMS[c["platform"]], c["name"], self._date(c["start"]), "Muted" if c.get("muted") else "On"))
                                   for c in sorted(data["contests"], key=lambda c: c["start"]) if c["end"] > self.service.now() and c["platform"] in data["preferences"]["platforms"]])
        for tree, label in ((self.tasks, self.task_empty), (self.alarms, self.alarm_empty), (self.contests, self.contest_empty)):
            if tree.get_children():
                label.place_forget()
            else:
                label.place(relx=0.5, rely=0.55, anchor="center")
        sources = {s["id"]: s for s in data["sources"]}
        lines = []
        for source in ("codeforces", "clist"):
            status = sources.get(source, {})
            updated = self._date(status.get("updated")) or "never"
            lines.append(f"{source.upper()} · Updated {updated}" + (" · " + status["error"] if status.get("error") else ""))
        if data["syncing"]:
            lines.append("Refreshing schedules…")
        self.source_status.configure(text="\n".join(lines))
        self.footer.configure(text=f"{data['preferences']['timezone']} · Saved on this device · Close this window to return to the tray")

    def _poll(self):
        if self._stopped:
            return
        try:
            data = self.service.snapshot()
            self._render(data)
            self._reminders(data)
        except Exception:
            logging.getLogger(__name__).exception("Could not update Planner windows")
        finally:
            if not self._stopped:
                self._after = self.root.after(500, self._poll)

    def _reminders(self, data):
        now = self.service.now()
        pending = [n for n in data["notifications"] if not n["dismissed"] and n["due"] <= now and (not n.get("expires") or n["expires"] > now)]
        pending.sort(key=lambda n: n["due"])
        ids = tuple((n["id"], n["revision"]) for n in pending)
        if ids != self._card_ids:
            self._card_ids = ids
            if self.card:
                self.card.destroy()
                self.card = None
            # No windows are mapped while dictation may still paste into the foreground.
            if pending and not self.audio_busy():
                self._show_card(pending)
        elif pending and self.card is None and not self.audio_busy():
            self._show_card(pending)
        # All simultaneously due reminders share one chime, avoiding an alert storm.
        active = set(ids)
        self._sound_state = {k: v for k, v in self._sound_state.items() if k in active}
        due_sounds = []
        for item in pending:
            key = (item["id"], item["revision"])
            state = self._sound_state.setdefault(key, [0, 0.0])
            if state[0] < 3 and time.monotonic() >= state[1]:
                due_sounds.append(state)
        if due_sounds and not self.audio_busy():
            if data["preferences"]["reminder_sound"]:
                if self.on_reminder_sound is not None:
                    if not self.on_reminder_sound():
                        return
                else:
                    self.sounds.play("reminder")
            for state in due_sounds:
                state[0] += 1
                state[1] = time.monotonic() + 10

    def _show_card(self, pending):
        self.card = tk.Toplevel(self.root)
        self.card.withdraw()
        self.card.overrideredirect(True)
        self.card.attributes("-topmost", True)
        p = lambda value: pixels(self.root, value)
        frame = ttk.Frame(self.card, padding=p(22), relief="solid", borderwidth=1, style="Surface.TFrame")
        frame.pack(fill="both", expand=True)
        first = pending[0]
        title = first["title"][:120] + ("…" if len(first["title"]) > 120 else "")
        ttk.Label(frame, text=title, font=("Segoe UI", 13, "bold"), wraplength=p(340), style="Surface.TLabel").pack(anchor="w")
        detail = "\n".join(first["detail"].splitlines()[:6])[:320]
        if len(pending) > 1:
            detail += f"\n\n+ {len(pending) - 1} more pending reminder(s)"
        ttk.Label(frame, text=detail, wraplength=p(340), justify="left", style="SurfaceMuted.TLabel").pack(anchor="w", pady=p(12))
        row = ttk.Frame(frame, style="Surface.TFrame")
        row.pack(fill="x")
        ttk.Button(row, text="Dismiss", style="Primary.TButton", command=lambda: self.service.acknowledge(first["id"])).pack(side="left", padx=(0, p(6)))
        ttk.Button(row, text="Snooze 5m", command=lambda: self.service.acknowledge(first["id"], True)).pack(side="left", padx=(0, 6))
        if first["url"]:
            ttk.Button(row, text="Open contest", command=lambda: self._open_reminder_url(first["url"])).pack(side="left")
        else:
            ttk.Button(row, text="Planner", command=self.open).pack(side="left")
        self.card.update_idletasks()
        width, height = self.card.winfo_reqwidth(), self.card.winfo_reqheight()
        x = max(0, self.root.winfo_screenwidth() - width - 28)
        y = max(0, self.root.winfo_screenheight() - height - 80)
        self.card.geometry(f"+{x}+{y}")
        show_without_activation(self.card)

    @staticmethod
    def _open_reminder_url(url):
        if any(safe_contest_url(url, p) for p in PLATFORMS):
            webbrowser.open(url)
