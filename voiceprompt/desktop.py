"""Qt desktop: a single main-thread UI over the existing application services."""
from __future__ import annotations

import queue
import time
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from PySide6.QtCore import QTimer, Qt, QUrl, QSize
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QSystemTrayIcon,
    QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from voiceprompt import __version__
from voiceprompt.config import save_settings
from voiceprompt.contests import PLATFORMS, safe_contest_url
from voiceprompt.planner import local_timestamp
from voiceprompt.recorder import microphones
from voiceprompt.release import releases_url


PAGES = ("Dictation", "History", "Tasks", "Focus timer", "Alarms", "Contests", "Settings")
STATUS_LABELS = {"idle": "Not prepared", "ready": "Ready to dictate", "loading model": "Preparing",
                 "starting": "Starting microphone", "recording": "Listening", "catching up": "Listening · catching up",
                 "transcribing": "Finishing recording", "cleaning": "Cleaning text", "error": "Needs attention"}
STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 11pt; color: #243D31; }
QMainWindow, QDialog, #workspace { background: #F5F7F4; }
QLabel { background: transparent; }
QLabel[role='title'] { font-size: 25pt; font-weight: 700; }
QLabel[role='heading'] { font-size: 15pt; font-weight: 600; }
QLabel[role='muted'] { color: #5C6D62; }
QLabel[role='measurement'] { font-size: 48pt; font-weight: 600; }
QListWidget#navigation { background: #EAF0E9; border: none; padding: 14px 10px; outline: none; }
QListWidget#navigation::item { padding: 13px 12px; margin-bottom: 3px; border: 1px solid transparent; }
QListWidget#navigation::item:selected { background: white; color: #285D46; font-weight: 600; }
QListWidget#navigation::item:hover { background: #DCEADC; }
QListWidget#navigation::item:focus { border: 1px solid #285D46; }
QFrame#rail { background: #EAF0E9; }
QPushButton, QToolButton { padding: 9px 14px; background: white; border: 1px solid #D6DFD5; border-radius: 4px; }
QPushButton:hover, QToolButton:hover { background: #EAF0E9; border-color: #5C6D62; }
QPushButton:pressed { background: #DCEADC; }
QPushButton:focus, QToolButton:focus { border: 2px solid #285D46; }
QPushButton[primary='true'] { background: #285D46; color: white; font-weight: 600; border-color: #285D46; }
QPushButton[primary='true']:hover { background: #1C4935; }
QPushButton:disabled, QToolButton:disabled { background: #EAF0E9; color: #5C6D62; border-color: #D6DFD5; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox { background: white; border: 1px solid #D6DFD5; border-radius: 3px; padding: 8px; selection-background-color: #DCEADC; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus { border: 2px solid #285D46; }
QComboBox:disabled, QSpinBox:disabled { color: #5C6D62; background: #EAF0E9; }
QComboBox::drop-down { border: none; width: 25px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #DCEADC; }
QCheckBox { spacing: 9px; padding: 6px 0; }
QCheckBox::indicator { width: 17px; height: 17px; }
QGroupBox { background: white; border: 1px solid #D6DFD5; border-radius: 5px; margin-top: 17px; padding: 20px 18px 14px; }
QGroupBox::title { subcontrol-origin: margin; left: 15px; padding: 0 6px; font-weight: 600; }
QTableWidget { background: white; alternate-background-color: #F7FAF6; border: 1px solid #D6DFD5; gridline-color: #D6DFD5; selection-background-color: #DCEADC; selection-color: #243D31; }
QTableWidget::item { padding: 8px; }
QHeaderView::section { background: #EAF0E9; border: none; border-bottom: 1px solid #D6DFD5; padding: 10px; font-weight: 600; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: #F5F7F4; }
QProgressBar { border: none; background: #EAF0E9; height: 7px; text-align: center; }
QProgressBar::chunk { background: #285D46; }
QMenu { background: white; border: 1px solid #D6DFD5; padding: 6px; }
QMenu::item { padding: 8px 20px; }
QMenu::item:selected { background: #DCEADC; }
"""


def label(text="", role=None):
    widget = QLabel(text)
    widget.setWordWrap(True)
    if role:
        widget.setProperty("role", role)
    return widget


def button(text, callback, *, primary=False):
    widget = QPushButton(text)
    widget.setProperty("primary", primary)
    widget.clicked.connect(lambda checked=False: callback())
    return widget


def row(*widgets):
    layout = QHBoxLayout()
    layout.setSpacing(10)
    for widget in widgets:
        layout.addWidget(widget)
    layout.addStretch()
    return layout


def spin(value, low=0, high=999):
    widget = QSpinBox()
    widget.setRange(low, high)
    widget.setValue(value)
    return widget


def combo(options, current):
    widget = QComboBox()
    widget.addItems(options)
    widget.setCurrentText(current)
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return widget


def microphone_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#285D46"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(1, 1, 62, 62, 14, 14)
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawRoundedRect(26, 13, 12, 23, 6, 6)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor("#FFFFFF"), 3))
    painter.drawArc(20, 23, 24, 21, 180 * 16, 180 * 16)
    painter.drawLine(32, 44, 32, 51)
    painter.drawLine(25, 51, 39, 51)
    painter.end()
    return QIcon(pixmap)


class FloatingStatus(QWidget):
    def __init__(self, controller, show_home):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.controller = controller
        self.show_home = show_home
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("floatingStatus")
        self.setStyleSheet("#floatingStatus { background: white; border: 1px solid #D6DFD5; border-radius: 8px; }")
        self.setAccessibleName("VoicePrompt recording status")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 9, 14, 9)
        self.text = label("VoicePrompt")
        self.text.setMinimumWidth(150)
        self.clock = label("", "muted")
        layout.addWidget(self.text)
        layout.addWidget(self.clock)
        self._drag = None
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def _menu(self, point):
        menu = QMenu(self)
        menu.addAction("Open VoicePrompt", self.show_home)
        menu.addAction("Cancel recording", self.controller.cancel_current)
        menu.exec(self.mapToGlobal(point))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event):
        if self._drag is not None:
            self._drag = None
            self.controller.update_pill_position(self.x(), self.y())

    def mouseDoubleClickEvent(self, event):
        self.show_home()

    def refresh(self):
        state = self.controller.get_status()
        text = STATUS_LABELS.get(state, state.title())
        self.text.setText(text)
        color = {"recording": "#AE3737", "catching up": "#94651C", "error": "#A43636", "transcribing": "#285E86"}.get(state, "#285D46")
        self.text.setStyleSheet(f"color: {color}; font-weight: 600;")
        seconds = int(self.controller.elapsed_seconds)
        self.clock.setText(f"{seconds // 60}:{seconds % 60:02}" if self.controller._session else "")
        self.setToolTip(self.controller.detail)
        self.adjustSize()


class ReminderCard(QWidget):
    def __init__(self, item, controller):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet("ReminderCard { background: white; border: 1px solid #D6DFD5; }")
        self.setFixedWidth(390)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.addWidget(label(item["title"], "heading"))
        layout.addWidget(label(item["detail"][:600], "muted"))
        layout.addLayout(row(button("Dismiss", lambda: controller.planner.acknowledge(item["id"]), primary=True),
                             button("Snooze 5 min", lambda: controller.planner.acknowledge(item["id"], True))))


class MainWindow(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("VoicePrompt")
        self.setWindowIcon(microphone_icon())
        self.resize(1120, 790)
        self.setMinimumSize(800, 560)
        self.tables = {}
        self.table_keys = {}
        self._last_history = None
        self._closed_for_quit = False
        self._settings_loaded = None
        self._last_refresh = 0
        self._task_for_timer = None
        central = QWidget()
        central.setObjectName("workspace")
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(205)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(10, 25, 10, 18)
        title = label("VoicePrompt", "heading")
        title.setContentsMargins(12, 0, 0, 20)
        rail_layout.addWidget(title)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setAccessibleName("Main navigation")
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.navigation.addItems(PAGES)
        rail_layout.addWidget(self.navigation, 1)
        rail_layout.addWidget(label("Local voice typing\nand daily focus", "muted"))
        rail_layout.addWidget(label(f"Version {__version__}", "muted"))
        layout.addWidget(rail)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(30, 24, 28, 14)
        content_layout.setSpacing(18)
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        self.footer = label("Saved on this device · Close this window to return to the tray", "muted")
        content_layout.addWidget(self.footer)
        layout.addWidget(content, 1)
        self.setCentralWidget(central)
        self.page_layouts = {}
        for name in PAGES:
            body = QWidget()
            page_layout = QVBoxLayout(body)
            page_layout.setContentsMargins(0, 0, 4, 0)
            page_layout.setSpacing(16)
            page_layout.addWidget(label(name if name != "Dictation" else "Your voice, at the cursor.", "title"))
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(body)
            self.stack.addWidget(scroll)
            self.page_layouts[name] = page_layout
        self._build_dictation()
        self._build_history()
        self._build_tasks()
        self._build_timer()
        self._build_alarms()
        self._build_contests()
        self._build_settings()
        self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        app_menu = self.menuBar().addMenu("VoicePrompt")
        app_menu.addAction("Check for updates", self.check_updates)
        app_menu.addAction("Pending reminders", self.show_reminders)
        app_menu.addSeparator()
        app_menu.addAction("Quit", controller.quit)
        self.refresh()

    def invoke(self, callback):
        try:
            callback()
            self.refresh(force=True)
        except Exception as exc:
            QMessageBox.warning(self, "VoicePrompt", str(exc))

    def show_page(self, name):
        self.navigation.setCurrentRow(PAGES.index(name))
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _build_dictation(self):
        layout = self.page_layouts["Dictation"]
        layout.addWidget(label("Hold your recording key, speak naturally, then release. VoicePrompt finishes your text and pastes it once.", "muted"))
        self.onboarding = QGroupBox("Set up voice typing")
        setup = QVBoxLayout(self.onboarding)
        setup.addWidget(label("1. Choose your microphone and check its level."))
        self.setup_microphone = combo(self._microphone_choices(), self.controller.settings.microphone or "Windows default")
        self.setup_microphone.setAccessibleName("Setup microphone")
        setup.addWidget(self.setup_microphone)
        setup.addLayout(row(button("Use this microphone", self.save_setup_microphone), button("Check microphone", self.controller.check_microphone)))
        setup.addWidget(label("2. Prepare the speech model. The first download may take a few minutes. Models are cached for offline use."))
        setup.addWidget(label("3. When Ready appears, try holding Right Ctrl in another text field. Release it to finish your sentence."))
        self.finish_setup = button("Finish setup", self.complete_setup, primary=True)
        setup.addLayout(row(self.finish_setup))
        layout.addWidget(self.onboarding)
        self.status_title = label("Not prepared", "heading")
        self.status_detail = label("", "muted")
        self.status_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status_title)
        layout.addWidget(self.status_detail)
        self.recording_time = label("0:00 / 5:00", "heading")
        layout.addWidget(self.recording_time)
        self.input_level = QProgressBar()
        self.input_level.setRange(0, 100)
        self.input_level.setTextVisible(False)
        self.input_level.setAccessibleName("Microphone input level")
        layout.addWidget(self.input_level)
        self.download = QProgressBar()
        self.download.setAccessibleName("Model download progress")
        layout.addWidget(self.download)
        self.prepare_button = button("Prepare model and microphone", self.controller.preload_model, primary=True)
        self.stop_button = button("Finish recording", self.controller.stop_recording)
        self.cancel_button = button("Cancel", self.controller.cancel_current)
        layout.addLayout(row(self.prepare_button, self.stop_button, self.cancel_button))
        self.recovery = QWidget()
        recovery_layout = QVBoxLayout(self.recovery)
        recovery_layout.setContentsMargins(0, 0, 0, 0)
        recovery_layout.addWidget(label("Your recording is held in memory until you retry, discard it, start another recording, or quit.", "muted"))
        recovery_layout.addLayout(row(button("Retry saved recording", self.controller.retry_failed, primary=True),
                                      button("Discard recording", self.controller.discard_failed)))
        layout.addWidget(self.recovery)
        layout.addWidget(label("Latest transcript", "heading"))
        self.latest = QPlainTextEdit()
        self.latest.setReadOnly(True)
        self.latest.setAccessibleName("Latest transcript")
        self.latest.setPlaceholderText("Your next transcript will appear here. You can copy it whenever you need.")
        self.latest.setMinimumHeight(140)
        layout.addWidget(self.latest, 1)
        self.copy_button = button("Copy text", lambda: self.copy_text(self.latest.toPlainText()))
        layout.addLayout(row(self.copy_button, button("Open history", lambda: self.show_page("History"))))
        self.hotkey_hint = label("", "muted")
        layout.addWidget(self.hotkey_hint)

    def _microphone_choices(self):
        try:
            return ["Windows default", *microphones()]
        except Exception:
            return ["Windows default"]

    def save_setup_microphone(self):
        value = self.setup_microphone.currentText()
        self.controller.update_settings(replace(self.controller.settings, microphone="" if value == "Windows default" else value))

    def complete_setup(self):
        self.controller.update_settings(replace(self.controller.settings, onboarding_completed=True))

    def copy_text(self, text):
        if text.strip():
            self.controller.injector.cancel_restore()
            QApplication.clipboard().setText(text)
            self.controller.detail = "Copied. Paste the text wherever you need it."

    def _table(self, name, headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(44)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setMinimumHeight(200)
        table.setAccessibleName(name)
        self.tables[name] = table
        self.page_layouts[name].addWidget(table, 1)
        return table

    def _populate(self, name, items, values):
        table = self.tables[name]
        key = repr(items)
        if self.table_keys.get(name) == key:
            return
        selected = self.selected(name)
        scroll = table.verticalScrollBar().value()
        table.setRowCount(len(items))
        for index, item in enumerate(items):
            for column, text in enumerate(values(item)):
                cell = QTableWidgetItem(str(text))
                cell.setData(Qt.ItemDataRole.UserRole, item)
                table.setItem(index, column, cell)
            if selected and item["id"] == selected["id"]:
                table.selectRow(index)
        table.verticalScrollBar().setValue(scroll)
        self.table_keys[name] = key

    def selected(self, name):
        table = self.tables[name]
        index = table.currentRow()
        cell = table.item(index, 0) if index >= 0 else None
        return cell.data(Qt.ItemDataRole.UserRole) if cell else None

    def _build_history(self):
        layout = self.page_layouts["History"]
        layout.addWidget(label("Transcripts stay on this device. Set the history limit to zero in Settings to stop saving future transcripts.", "muted"))
        self._table("History", ["Recorded", "Transcript", "Speech engine"])
        layout.addLayout(row(button("Copy selected", lambda: self.copy_text((self.selected("History") or {}).get("text", ""))),
                             button("Clear history", self.clear_history)))
        self.history_empty = label("No transcripts yet. Your first completed dictation will appear here.", "muted")
        layout.addWidget(self.history_empty)

    def clear_history(self):
        if QMessageBox.question(self, "Clear history", "Delete all saved transcripts on this device?") == QMessageBox.StandardButton.Yes:
            self.controller.history.clear()
            self.refresh(force=True)

    def _planner_available(self):
        if self.controller.planner is None:
            raise ValueError(self.controller._planner_error or "Planner storage is unavailable. Your data has been kept.")
        return self.controller.planner

    def _build_tasks(self):
        layout = self.page_layouts["Tasks"]
        layout.addWidget(label("A place for the next thing. Add a task, then give it a focused block of time.", "muted"))
        self.quick_task = QLineEdit()
        self.quick_task.setPlaceholderText("What would you like to work on?")
        self.quick_task.setAccessibleName("New task")
        self.quick_task.returnPressed.connect(lambda: self.invoke(self.add_quick_task))
        quick = QHBoxLayout()
        quick.addWidget(self.quick_task, 1)
        quick.addWidget(button("Add task", lambda: self.invoke(self.add_quick_task), primary=True))
        quick.addWidget(button("Add with details", lambda: self.task_editor()))
        layout.addLayout(quick)
        self._table("Tasks", ["Task", "Status", "Reminder"])
        layout.addLayout(row(button("Complete / reopen", lambda: self.task_action("complete")),
                             button("Start a timer", self.timer_for_task), button("Edit", lambda: self.task_editor(self.selected("Tasks"))),
                             button("Delete", lambda: self.delete_item("Tasks", "task"))))
        self.task_empty = label("Add your first task above. Tasks and timers work offline.", "muted")
        layout.addWidget(self.task_empty)

    def add_quick_task(self):
        self._planner_available().save_task(self.quick_task.text())
        self.quick_task.clear()

    def task_action(self, action):
        item = self.selected("Tasks")
        if item:
            self.invoke(lambda: self._planner_available().complete_task(item["id"]))

    def delete_item(self, page, kind):
        item = self.selected(page)
        if item and QMessageBox.question(self, "Delete item", f"Delete ‘{item['title']}’?") == QMessageBox.StandardButton.Yes:
            self.invoke(lambda: self._planner_available().delete(kind, item["id"]))

    def _editor(self, title):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(530, 380)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setSpacing(12)
        layout.addLayout(form)
        return dialog, layout, form

    def _editor_save(self, dialog, layout, callback):
        error = label("", "muted")
        layout.addWidget(error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        def save():
            try:
                callback()
                dialog.accept()
                self.refresh(force=True)
            except Exception as exc:
                error.setText(str(exc))
        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        dialog.exec()

    def task_editor(self, item=None):
        dialog, layout, form = self._editor("Edit task" if item else "Add task")
        title = QLineEdit(item["title"] if item else "")
        notes = QPlainTextEdit(item.get("notes", "") if item else "")
        due = QLineEdit(self.date_text(item.get("due")) if item else "")
        due.setPlaceholderText("Optional: YYYY-MM-DD HH:MM")
        form.addRow("Task", title)
        form.addRow("Notes", notes)
        form.addRow("Reminder", due)
        self._editor_save(dialog, layout, lambda: self._planner_available().save_task(
            title.text(), notes.toPlainText(), self.parse_date(due.text()) if due.text().strip() else None,
            item["id"] if item else None))

    def timer_for_task(self):
        item = self.selected("Tasks")
        if item:
            self.timer_title.setText(item["title"])
            self._task_for_timer = item["id"]
            self.show_page("Focus timer")
            self.timer_hours.setFocus()

    def _build_timer(self):
        layout = self.page_layouts["Focus timer"]
        layout.addWidget(label("Give one activity your attention. Choose any duration, or use work and break cycles.", "muted"))
        self.timer_display = label("25:00", "measurement")
        self.timer_state = label("No active session", "muted")
        layout.addWidget(self.timer_display)
        layout.addWidget(self.timer_state)
        self.timer_progress = QProgressBar()
        self.timer_progress.setTextVisible(False)
        self.timer_progress.setAccessibleName("Focus session progress")
        layout.addWidget(self.timer_progress)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setSpacing(12)
        self.timer_title = QLineEdit("Focus session")
        self.timer_hours, self.timer_minutes = spin(0), spin(25, 0, 59)
        duration = QWidget()
        duration_layout = QHBoxLayout(duration)
        duration_layout.setContentsMargins(0, 0, 0, 0)
        duration_layout.addWidget(self.timer_hours)
        duration_layout.addWidget(label("hours"))
        duration_layout.addWidget(self.timer_minutes)
        duration_layout.addWidget(label("minutes"))
        form.addRow("Activity", self.timer_title)
        form.addRow("Duration", duration)
        layout.addLayout(form)
        layout.addLayout(row(*[button(f"{minutes} min", lambda m=minutes: self.set_duration(m)) for minutes in (25, 45, 60, 90)]))
        self.pomodoro = QCheckBox("Use Pomodoro work / break cycles")
        self.pomodoro_options = QWidget()
        cycle = QFormLayout(self.pomodoro_options)
        cycle.setContentsMargins(0, 0, 0, 0)
        self.short_break, self.long_break, self.rounds = spin(5, 1, 180), spin(15, 1, 180), spin(4, 1, 100)
        cycle.addRow("Short break (minutes)", self.short_break)
        cycle.addRow("Long break (minutes)", self.long_break)
        cycle.addRow("Work rounds", self.rounds)
        self.pomodoro.toggled.connect(self.pomodoro_options.setVisible)
        self.pomodoro_options.hide()
        layout.addWidget(self.pomodoro)
        layout.addWidget(self.pomodoro_options)
        self.timer_actions = {}
        actions = QHBoxLayout()
        actions.addWidget(button("Start session", self.start_timer, primary=True))
        for action in ("pause", "resume", "restart", "cancel"):
            self.timer_actions[action] = button(action.capitalize(), lambda a=action: self.invoke(lambda: self._planner_available().timer_action(a)))
            actions.addWidget(self.timer_actions[action])
        actions.addStretch()
        layout.addLayout(actions)
        layout.addStretch()

    def set_duration(self, minutes):
        self.timer_hours.setValue(minutes // 60)
        self.timer_minutes.setValue(minutes % 60)

    def start_timer(self):
        def start():
            planner = self._planner_available()
            old = planner.snapshot()["timer"]
            replace_existing = bool(old and old["status"] in {"running", "paused"})
            if replace_existing and QMessageBox.question(self, "Replace session", "Replace the active timer with this session?") != QMessageBox.StandardButton.Yes:
                return
            planner.start_timer(self.timer_title.text(), self.timer_hours.value() * 3600 + self.timer_minutes.value() * 60,
                                mode="pomodoro" if self.pomodoro.isChecked() else "countdown",
                                short_break=self.short_break.value() * 60, long_break=self.long_break.value() * 60,
                                rounds=self.rounds.value(), task_id=self._task_for_timer, replace=replace_existing)
        self.invoke(start)

    def _build_alarms(self):
        layout = self.page_layouts["Alarms"]
        layout.addWidget(label("One-time and repeating reminders. VoicePrompt must be running and your computer awake for an alarm to sound.", "muted"))
        self._table("Alarms", ["Alarm", "Next time", "Repeats", "Status"])
        layout.addLayout(row(button("Add alarm", self.alarm_editor, primary=True),
                             button("Edit", lambda: self.alarm_editor(self.selected("Alarms"))),
                             button("Enable / disable", self.toggle_alarm), button("Delete", lambda: self.delete_item("Alarms", "alarm"))))
        self.alarm_empty = label("No alarms yet. Add a time you would like to remember.", "muted")
        layout.addWidget(self.alarm_empty)

    def alarm_editor(self, item=None):
        dialog, layout, form = self._editor("Edit alarm" if item else "Add alarm")
        title = QLineEdit(item["title"] if item else "")
        zone = self._planner_available().preferences()["timezone"]
        default = (datetime.now(ZoneInfo(zone)) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        due = QLineEdit(self.date_text(item["due"]) if item else default)
        form.addRow("Alarm", title)
        form.addRow("Time (YYYY-MM-DD HH:MM)", due)
        days = QWidget()
        day_layout = QHBoxLayout(days)
        day_layout.setContentsMargins(0, 0, 0, 0)
        checks = []
        for index, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            check = QCheckBox(name)
            check.setChecked(bool(item and index in item.get("weekdays", [])))
            day_layout.addWidget(check)
            checks.append(check)
        form.addRow("Repeat on", days)
        layout.addWidget(label("Leave all days unchecked for a one-time alarm.", "muted"))
        self._editor_save(dialog, layout, lambda: self._planner_available().save_alarm(title.text(), self.parse_date(due.text()),
                           [i for i, check in enumerate(checks) if check.isChecked()], item["id"] if item else None))

    def toggle_alarm(self):
        item = self.selected("Alarms")
        if item:
            self.invoke(lambda: self._planner_available().toggle_alarm(item["id"]))

    def _build_contests(self):
        layout = self.page_layouts["Contests"]
        layout.addWidget(label("Upcoming and ongoing programming contests. Codeforces needs no key; other platforms use your CLIST connection.", "muted"))
        self._table("Contests", ["Contest", "Platform", "Starts", "Reminder"])
        layout.addLayout(row(button("Open contest", self.open_contest, primary=True), button("Mute / unmute", self.mute_contest),
                             button("Refresh", lambda: self.invoke(lambda: self._planner_available().refresh_contests(True))),
                             button("Connect CLIST", self.connect_clist)))
        self.contest_status = label("", "muted")
        layout.addWidget(self.contest_status)
        layout.addWidget(button("Reminder settings", self.reminder_settings))

    def open_contest(self):
        item = self.selected("Contests")
        if item and safe_contest_url(item["url"], item["platform"]):
            QDesktopServices.openUrl(QUrl(item["url"]))

    def mute_contest(self):
        item = self.selected("Contests")
        if item:
            self.invoke(lambda: self._planner_available().mute_contest(item["id"]))

    def connect_clist(self):
        dialog, layout, form = self._editor("Connect CLIST")
        user = QLineEdit(self._planner_available().preferences()["clist_username"])
        key = QLineEdit()
        key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("CLIST username", user)
        form.addRow("API key", key)
        layout.addWidget(label("The key is stored in Windows Credential Manager. Connection results appear under the contest list.", "muted"))
        self._editor_save(dialog, layout, lambda: self._planner_available().connect_clist(user.text(), key.text()))

    def reminder_settings(self):
        prefs = self._planner_available().preferences()
        dialog, layout, form = self._editor("Reminder settings")
        zone = QLineEdit(prefs["timezone"])
        lead, hour = spin(prefs["contest_minutes"], 0, 10080), spin(prefs["summary_hour"], 0, 23)
        daily, sound = QCheckBox("Daily contest summary"), QCheckBox("Play reminder sounds")
        daily.setChecked(prefs["daily_summary"])
        sound.setChecked(prefs["reminder_sound"])
        form.addRow("Timezone", zone)
        form.addRow("Contest lead (minutes)", lead)
        form.addRow("Summary hour", hour)
        form.addRow(daily)
        form.addRow(sound)
        platforms = {}
        for key, name in PLATFORMS.items():
            check = QCheckBox(name)
            check.setChecked(key in prefs["platforms"])
            form.addRow(check)
            platforms[key] = check
        self._editor_save(dialog, layout, lambda: self._planner_available().update_preferences(
            timezone=zone.text().strip(), contest_minutes=lead.value(), summary_hour=hour.value(), daily_summary=daily.isChecked(),
            reminder_sound=sound.isChecked(), platforms=[key for key, check in platforms.items() if check.isChecked()]))

    def _build_settings(self):
        layout = self.page_layouts["Settings"]
        layout.addWidget(label("Keep everyday controls close. Speech-engine tuning is available under Advanced.", "muted"))
        settings = self.controller.settings
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setSpacing(12)
        self.fields = {}
        choices = {
            "hotkey": ["right_ctrl", "left_ctrl", "right_alt", "left_alt", "f8", "f9"],
            "recording_mode": ["ptt", "toggle"],
            "microphone": self._microphone_choices(),
            "capture_mode": ["auto", "wasapi", "mme"],
            "backend": ["whisper", "nemotron", "parakeet", "moonshine"],
            "nemotron_device": ["vulkan", "cpu"],
            "model": ["base.en", "tiny.en", "small.en", "Systran/faster-distil-whisper-small.en", "small", "base", "tiny"],
            "streaming_model": ["tiny", "small"], "language": ["en", "auto"],
        }
        def field(name, text, target=form):
            value = getattr(settings, name)
            if name in choices:
                if name == "microphone":
                    value = value or "Windows default"
                elif name == "language":
                    value = value or "auto"
                options = list(dict.fromkeys([*choices[name], str(value)]))
                widget = combo(options, str(value))
                if name in {"hotkey", "recording_mode"}:
                    names = {"right_ctrl": "Right Ctrl", "left_ctrl": "Left Ctrl", "right_alt": "Right Alt", "left_alt": "Left Alt",
                             "f8": "F8", "f9": "F9", "ptt": "Hold to talk", "toggle": "Press to start / stop"}
                    for index in range(widget.count()):
                        raw = widget.itemText(index)
                        widget.setItemData(index, raw)
                        widget.setItemText(index, names.get(raw, raw))
            elif isinstance(value, bool):
                widget = QCheckBox(text)
                widget.setChecked(value)
            elif isinstance(value, int):
                widget = spin(value, 0 if name == "max_history" else 1, 500 if name == "max_history" else 12)
            else:
                widget = QLineEdit(str(value))
            widget.setAccessibleName(text)
            self.fields[name] = widget
            target.addRow(widget) if isinstance(widget, QCheckBox) else target.addRow(text, widget)
        for name, text in (("microphone", "Microphone"), ("hotkey", "Recording key"), ("recording_mode", "Recording mode"),
                           ("sound_feedback", "Play recording sounds"), ("startup_on_boot", "Start after Windows sign-in"),
                           ("paste_injection", "Paste completed text automatically"), ("preserve_clipboard", "Restore clipboard after automatic paste"),
                           ("max_history", "Saved transcripts (0 disables history)")):
            field(name, text)
        layout.addLayout(form)
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("Advanced speech settings")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced = QWidget()
        advanced_form = QFormLayout(self.advanced)
        advanced_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        advanced_form.setContentsMargins(0, 0, 0, 0)
        advanced_form.setSpacing(12)
        for name, text in (("backend", "Speech engine"), ("nemotron_device", "Nemotron processing"), ("model", "Whisper model"),
                           ("streaming_model", "Moonshine model"), ("language", "Whisper language"), ("beam_size", "Whisper beam size"),
                           ("cpu_threads", "CPU threads"), ("capture_mode", "Capture API"), ("preload_model", "Prepare automatically at startup"),
                           ("noise_suppression", "Use optional RNNoise suppression"), ("vad_filter", "Whisper: filter silence")):
            field(name, text, advanced_form)
        self.fields["beam_size"].setMaximum(5)
        advanced_form.addRow(label("Models download on first use. Keep noise suppression off until it improves recognition on your microphone.", "muted"))
        self.advanced_toggle.toggled.connect(self.advanced.setVisible)
        self.advanced_toggle.toggled.connect(lambda opened: self.advanced_toggle.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow))
        self.advanced.hide()
        layout.addWidget(self.advanced_toggle)
        layout.addWidget(self.advanced)
        layout.addWidget(label("Dictionary", "heading"))
        layout.addWidget(label("One source=target replacement per line. Your names and terminology remain local.", "muted"))
        self.dictionary = QPlainTextEdit("\n".join(f"{key}={value}" for key, value in settings.replacements.items()))
        self.dictionary.setAccessibleName("Dictionary replacements")
        self.dictionary.setMinimumHeight(130)
        layout.addWidget(self.dictionary)

        self.settings_message = label("", "muted")
        layout.addWidget(self.settings_message)
        layout.addLayout(row(button("Save settings", self.save_preferences, primary=True), button("Check for updates", self.check_updates)))
        layout.addStretch()
        self.fields["backend"].currentTextChanged.connect(self._engine_controls)
        self._engine_controls()

    def _engine_controls(self):
        backend = self.fields["backend"].currentText()
        for name in ("model", "language", "beam_size", "vad_filter"):
            self.fields[name].setEnabled(backend == "whisper")
        self.fields["streaming_model"].setEnabled(backend == "moonshine")
        self.fields["nemotron_device"].setEnabled(backend == "nemotron")

    def save_preferences(self):
        try:
            values = {}
            for name, widget in self.fields.items():
                values[name] = widget.isChecked() if isinstance(widget, QCheckBox) else widget.value() if isinstance(widget, QSpinBox) else widget.currentText() if isinstance(widget, QComboBox) else widget.text()
            values["microphone"] = "" if values["microphone"] == "Windows default" else values["microphone"]
            for name in ("hotkey", "recording_mode"):
                values[name] = self.fields[name].currentData()
            values["language"] = "" if values["language"] == "auto" else values["language"]
            pairs = {}
            for line in self.dictionary.toPlainText().splitlines():
                if not line.strip():
                    continue
                source, separator, target = line.partition("=")
                if not separator or not source.strip() or not target.strip():
                    raise ValueError("Use source=target for every dictionary replacement.")
                pairs[source.strip()] = target.strip()

            self.controller.update_settings(replace(self.controller.settings, replacements=pairs, **values))
            self.settings_message.setText("Settings queued until this session finishes." if self.controller._session else "Saving preferences and preparing the selected engine…")
        except Exception as exc:
            self.settings_message.setText(str(exc))

    def check_updates(self):
        url = releases_url()
        if url:
            QDesktopServices.openUrl(QUrl(url))
        else:
            QMessageBox.information(self, "Updates", "This development build has no release repository configured.")

    def date_text(self, value):
        if value is None:
            return ""
        zone = self.controller.planner.preferences()["timezone"] if self.controller.planner else "Asia/Kolkata"
        return datetime.fromtimestamp(value, ZoneInfo(zone)).strftime("%Y-%m-%d %H:%M")

    def parse_date(self, value):
        return local_timestamp(value, self._planner_available().preferences()["timezone"])

    def show_reminders(self):
        planner = self._planner_available()
        dialog, layout, form = self._editor("Pending reminders")
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["Reminder", "Due"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        pending = [item for item in planner.snapshot()["notifications"] if not item["dismissed"]]
        table.setRowCount(len(pending))
        for index, item in enumerate(pending):
            table.setItem(index, 0, QTableWidgetItem(item["title"]))
            table.setItem(index, 1, QTableWidgetItem(self.date_text(item["due"])))
        layout.addWidget(table)
        if not pending:
            layout.addWidget(label("No pending reminders.", "muted"))
        def acknowledge(snooze):
            index = table.currentRow()
            if index >= 0:
                planner.acknowledge(pending[index]["id"], snooze)
                dialog.accept()
        layout.addLayout(row(button("Dismiss", lambda: acknowledge(False)), button("Snooze 5 min", lambda: acknowledge(True)), button("Close", dialog.reject)))
        dialog.exec()

    def refresh(self, force=False):
        controller = self.controller
        status = controller.get_status()
        self.status_title.setText(STATUS_LABELS.get(status, status.title()))
        self.status_detail.setText(controller.last_error or controller.detail)
        self.status_title.setStyleSheet("color: #A43636;" if controller.last_error else "")
        elapsed = int(controller.elapsed_seconds)
        self.recording_time.setText(f"{elapsed // 60}:{elapsed % 60:02} / 5:00")
        self.input_level.setValue(int(controller.recorder.level * 100) if isinstance(controller.recorder.level, (int, float)) and controller.recorder.is_recording else 0)
        self.prepare_button.setEnabled(not controller._working)
        self.cancel_button.setEnabled(controller._working)
        self.stop_button.setEnabled(controller._session is not None and not controller._session.release.is_set())
        self.recovery.setVisible(bool(controller._failed_audio))
        self.onboarding.setVisible(not controller.settings.onboarding_completed)
        self.finish_setup.setEnabled(controller._ready and not controller._working)
        self.hotkey_hint.setText(f"Recording key: {controller.settings.hotkey.replace('_', ' ').title()} · {'Hold to talk' if controller.settings.recording_mode == 'ptt' else 'Press to start / stop'} · Audio stays on your device")
        if controller.latest_text != self.latest.toPlainText():
            self.latest.setPlainText(controller.latest_text)
        self.copy_button.setEnabled(bool(controller.latest_text.strip()))
        progress = controller.download_progress
        self.download.setVisible(status == "loading model")
        total = progress.get("total")
        if total:
            self.download.setRange(0, 100)
            self.download.setValue(min(100, int(progress.get("completed", 0) / total * 100)))
            self.download.setFormat(f"{self.download.value()}% · {progress.get('name', 'Model download')}")
        else:
            self.download.setRange(0, 0)
        if not force and time.monotonic() - self._last_refresh < 0.5:
            return
        self._last_refresh = time.monotonic()
        from dataclasses import asdict
        history = [asdict(item) for item in controller.history.load()]
        self._populate("History", history, lambda item: (item["created_at"][:16].replace("T", " ") + " UTC", item["text"], item["source"]))
        self.history_empty.setVisible(not history)
        if not controller.planner:
            self.footer.setText(controller._planner_error)
            return
        data = controller.planner.snapshot()
        self._populate("Tasks", data["tasks"], lambda item: (item["title"], "Done" if item["done"] else "To do", self.date_text(item["due"]) or "—"))
        self.task_empty.setVisible(not data["tasks"])
        days = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        self._populate("Alarms", data["alarms"], lambda item: (item["title"], self.date_text(item["due"]), ", ".join(days[i] for i in item["weekdays"]) or "Once", "On" if item["enabled"] else "Off"))
        self.alarm_empty.setVisible(not data["alarms"])
        now = controller.planner.now()
        contests = sorted([item for item in data["contests"] if item["end"] > now and item["platform"] in data["preferences"]["platforms"]], key=lambda item: item["start"])
        self._populate("Contests", contests, lambda item: (item["name"], PLATFORMS[item["platform"]], self.date_text(item["start"]), "Muted" if item.get("muted") else "On"))
        sources = [f"{item['id'].capitalize()}: {item['error'] or 'Updated ' + self.date_text(item['updated'])}" for item in data["sources"]]
        if data["syncing"]:
            sources.append("Refreshing schedules…")
        self.contest_status.setText("\n".join(sources) or "No cached contests yet. Refresh schedules or connect CLIST.")
        timer = data["timer"]
        remaining = max(0, int(timer["remaining"])) if timer else 1500
        self.timer_display.setText(f"{remaining // 3600}:{remaining // 60 % 60:02}:{remaining % 60:02}" if remaining >= 3600 else f"{remaining // 60:02}:{remaining % 60:02}")
        self.timer_state.setText(f"{timer['title']} · {timer['status'].capitalize()} · {timer['phase'].replace('_', ' ')}" if timer else "No active session")
        for action, control in self.timer_actions.items():
            control.setEnabled(bool(timer and (timer["status"] == "running" if action == "pause" else timer["status"] == "paused" if action == "resume" else timer["status"] in {"running", "paused"} if action == "cancel" else True)))
        duration = timer.get(timer["phase"], timer["work"]) if timer else 1500
        self.timer_progress.setValue(int(max(0, min(100, (1 - remaining / max(1, duration)) * 100))) if timer else 0)
        self.footer.setText(f"{data['preferences']['timezone']} · Saved on this device · Close this window to return to the tray")

    def closeEvent(self, event):
        if self._closed_for_quit:
            event.accept()
        elif QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
            event.ignore()
        else:
            self.controller.quit()
            event.accept()


class DesktopHost:
    def __init__(self, controller, adapter):
        self.controller, self.adapter = controller, adapter
        self.app = QApplication.instance() or QApplication([])
        self.app.setApplicationName("VoicePrompt")
        self.app.setApplicationVersion(__version__)
        self.app.setQuitOnLastWindowClosed(False)
        # Qt's offscreen Windows plugin does not enumerate the system font store.
        # Load installed fonts for headless previews, without bundling font files.
        if "Segoe UI" not in QFontDatabase.families():
            import os
            from pathlib import Path
            fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
            for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
                if (fonts / name).is_file():
                    QFontDatabase.addApplicationFont(str(fonts / name))
        self.app.setFont(QFont("Segoe UI", 11))
        self.app.setStyle("Fusion")
        self.app.setStyleSheet(STYLE)
        self.window = MainWindow(controller)
        self.pill = FloatingStatus(controller, lambda: self.window.show_page("Dictation"))
        self.tray = QSystemTrayIcon(microphone_icon(), self.window)
        menu = QMenu()
        menu.addAction("Open VoicePrompt", lambda: self.window.show_page("Dictation"))
        menu.addAction("Tasks & timers", lambda: self.window.show_page("Tasks"))
        menu.addAction("Settings", lambda: self.window.show_page("Settings"))
        menu.addAction("Prepare model", controller.preload_model)
        menu.addAction("Cancel recording", controller.cancel_current)
        menu.addAction("Check for updates", self.window.check_updates)
        menu.addSeparator()
        menu.addAction("Quit", controller.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.window.show_page("Dictation") if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.timer = QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        self.card = None
        self._card_key = None
        self._sound_state = {}

    def show_page(self, name):
        self.window.show_page(name)

    def run(self):
        self.tray.show()
        self.window.show()
        screen = self.app.primaryScreen().availableGeometry()
        self.window.resize(min(1120, screen.width() - 50), min(790, screen.height() - 50))
        settings = self.controller.settings
        self.pill.adjustSize()
        x = settings.pill_position_x if settings.pill_position_x >= 0 else screen.right() - self.pill.width() - 25
        y = settings.pill_position_y if settings.pill_position_y >= 0 else screen.bottom() - self.pill.height() - 25
        self.pill.move(max(screen.left(), min(x, screen.right() - self.pill.width())), max(screen.top(), min(y, screen.bottom() - self.pill.height())))
        self.pill.show()
        self.controller._planner_root_ready(None)
        self.timer.start()
        self.app.exec()

    def poll(self):
        if not self.controller._quitting and getattr(self.controller, "shutdown_requested", lambda: False)():
            self.controller.quit()
            return
        while True:
            try:
                self.adapter.events.get_nowait()()
            except queue.Empty:
                break
        if self.controller._quitting:
            return
        self.window.refresh()
        self.pill.refresh()
        self.tray.setToolTip(f"VoicePrompt · {STATUS_LABELS.get(self.controller.status, self.controller.status)}")
        self._reminders()

    def _reminders(self):
        planner = self.controller.planner
        if not planner:
            return
        data = planner.snapshot()
        now = planner.now()
        pending = sorted([item for item in data["notifications"] if not item["dismissed"] and item["due"] <= now and (not item.get("expires") or item["expires"] > now)], key=lambda item: item["due"])
        busy = self.controller._reminder_audio_busy()
        item = pending[0] if pending and not busy else None
        key = (item["id"], item["revision"]) if item else None
        if key != self._card_key:
            if self.card:
                self.card.close()
                self.card.deleteLater()
                self.card = None
            self._card_key = key
            if item:
                self.card = ReminderCard(item, self.controller)
                self.card.adjustSize()
                screen = self.app.primaryScreen().availableGeometry()
                self.card.move(screen.right() - self.card.width() - 25, screen.bottom() - self.card.height() - 85)
                self.card.show()
        active = {(n["id"], n["revision"]) for n in pending}
        self._sound_state = {key: value for key, value in self._sound_state.items() if key in active}
        if not busy:
            due = []
            for n in pending:
                key = (n["id"], n["revision"])
                count, last = self._sound_state.get(key, (0, 0))
                if count < 3 and time.monotonic() - last >= 10:
                    due.append((key, count))
            if due and (not data["preferences"]["reminder_sound"] or self.controller._play_reminder_sound()):
                for key, count in due:
                    self._sound_state[key] = (count + 1, time.monotonic())

    def stop(self):
        self.timer.stop()
        self.tray.hide()
        if self.card:
            self.card.close()
        self.pill.close()
        self.window._closed_for_quit = True
        self.window.close()
        self.app.quit()
