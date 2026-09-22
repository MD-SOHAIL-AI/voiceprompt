from __future__ import annotations

import math
import queue
import tkinter as tk
from collections import deque
from collections.abc import Callable
from dataclasses import replace
from tkinter import messagebox, ttk

import pystray
from PIL import Image, ImageDraw

from voiceprompt.config import Settings

HOTKEYS = ["right_ctrl", "left_ctrl", "right_alt", "left_alt", "f8", "f9"]
ASR_BACKENDS = ["auto", "faster_whisper", "whisper_cpp"]
MODELS = ["base", "small", "tiny", "Systran/faster-distil-whisper-small.en", "base.en", "small.en", "tiny.en"]
LANGUAGES = ["auto", "en", "ta", "hi", "te", "ml", "kn"]
RECORDING_MODES = ["ptt", "toggle"]
CLEANUP_PROVIDERS = ["none", "openrouter", "gemini"]


class FloatingPill:
    """Small always-on-top waveform capsule.

    Recording bars are driven only by recent microphone levels. Synthetic
    animation is used only for non-recording states where there is no live
    microphone signal to visualize.
    """

    PILL_W_IDLE = 48
    PILL_W_ACTIVE = 176
    PILL_H = 44
    WAVE_Y = PILL_H // 2
    WAVE_X0 = 14
    BAR_COUNT = 24
    BAR_W = 3
    BAR_GAP = 6
    BAR_MIN_H = 3
    BAR_MAX_H = 28
    DOT_COUNT = 4
    DOT_R = 4

    _PALETTE: dict[str, tuple[str, str]] = {
        "idle": ("#374151", "#6b7280"),
        "ready": ("#22c55e", "#22c55e"),
        "recording": ("#22c55e", "#4ade80"),
        "transcribing": ("#0ea5e9", "#38bdf8"),
        "cleaning": ("#a78bfa", "#c4b5fd"),
        "loading model": ("#f59e0b", "#fbbf24"),
        "error": ("#ef4444", "#f87171"),
    }

    def __init__(
        self,
        get_settings: Callable[[], Settings],
        on_open_settings: Callable[[], None],
        on_retry: Callable[[], None],
        on_quit: Callable[[], None],
        on_moved: Callable[[int, int], None],
    ) -> None:
        self.get_settings = get_settings
        self.on_open_settings = on_open_settings
        self.on_retry = on_retry
        self.on_quit = on_quit
        self.on_moved = on_moved
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._root: tk.Tk | None = None
        self._canvas: tk.Canvas | None = None
        self._menu: tk.Menu | None = None
        self._status = "idle"
        self._tick = 0
        self._drag_start: tuple[int, int] | None = None
        self._audio_history: deque[float] = deque([0.0] * self.BAR_COUNT, maxlen=self.BAR_COUNT)
        self._bar_heights = [float(self.BAR_MIN_H)] * self.BAR_COUNT
        self._bar_targets = [float(self.BAR_MIN_H)] * self.BAR_COUNT
        self._settings_window: SettingsWindow | None = None

    def run(self) -> None:
        settings = self.get_settings()
        root = tk.Tk()
        self._root = root
        root.title("Voice Prompt")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg="#ff00ff")
        try:
            root.attributes("-transparentcolor", "#ff00ff")
        except tk.TclError:
            pass

        x = settings.pill_position_x if settings.pill_position_x >= 0 else 90
        y = settings.pill_position_y if settings.pill_position_y >= 0 else 520
        root.geometry(f"{self.PILL_W_IDLE}x{self.PILL_H}+{x}+{y}")
        canvas = tk.Canvas(
            root,
            width=self.PILL_W_IDLE,
            height=self.PILL_H,
            bg="#ff00ff",
            highlightthickness=0,
            bd=0,
        )
        canvas.pack(fill="both", expand=True)
        self._canvas = canvas

        canvas.bind("<ButtonPress-1>", self._start_drag)
        canvas.bind("<B1-Motion>", self._drag)
        canvas.bind("<ButtonRelease-1>", self._end_drag)
        canvas.bind("<Button-3>", self._show_menu)
        canvas.bind("<Double-Button-1>", lambda event: self.on_open_settings())

        self._menu = tk.Menu(root, tearoff=False)
        self._menu.add_command(label="Open settings", command=self.on_open_settings)
        self._menu.add_command(label="Retry last transcription", command=self.on_retry)
        self._menu.add_separator()
        self._menu.add_command(label="Quit", command=self.on_quit)

        self._draw()
        self._poll()
        self._animate()
        root.mainloop()

    def stop(self) -> None:
        self._events.put(("stop", None))

    def set_status(self, status: str) -> None:
        self._events.put(("status", status))

    def set_audio_level(self, level: float) -> None:
        # Keep the audio callback cheap; Tk consumes these values on its UI thread.
        self._events.put(("audio", max(0.0, min(1.0, float(level)))))

    def open_settings_window(self, on_save: Callable[[Settings], None]) -> None:
        self._events.put(("settings", on_save))

    def _poll(self) -> None:
        while True:
            try:
                name, payload = self._events.get_nowait()
            except queue.Empty:
                break

            if name == "status":
                previous = self._status
                self._status = str(payload)
                if previous != self._status:
                    if self._status == "recording":
                        self._audio_history = deque([0.0] * self.BAR_COUNT, maxlen=self.BAR_COUNT)
                    self._resize_pill()
                self._draw()
            elif name == "audio":
                self._audio_history.append(float(payload))
            elif name == "settings" and self._root:
                if self._settings_window is None or not self._settings_window.is_open:
                    self._settings_window = SettingsWindow(self.get_settings(), payload)  # type: ignore[arg-type]
                    self._settings_window.show(self._root)
                else:
                    self._settings_window.focus()
            elif name == "stop" and self._root:
                self._root.destroy()
                return

        if self._root:
            self._root.after(40, self._poll)

    def _animate(self) -> None:
        self._tick += 1
        self._update_bar_targets()
        self._step_bars()
        self._draw()
        if self._root:
            self._root.after(40, self._animate)  # ~25 fps

    def _resize_pill(self) -> None:
        if not self._root or not self._canvas:
            return
        width = self.PILL_W_IDLE if self._status in {"idle", "ready"} else self.PILL_W_ACTIVE
        self._root.geometry(f"{width}x{self.PILL_H}+{self._root.winfo_x()}+{self._root.winfo_y()}")
        self._canvas.config(width=width, height=self.PILL_H)

    def _update_bar_targets(self) -> None:
        if self._status == "recording":
            # Every bar is a real recent microphone loudness sample. The left
            # side is older audio; the right side is the newest audio.
            values = list(self._audio_history)
            span = self.BAR_MAX_H - self.BAR_MIN_H
            for i, level in enumerate(values):
                # Mild perceptual compression keeps quiet speech visible while
                # preserving the difference between quiet and loud syllables.
                shaped = math.pow(max(0.0, min(1.0, level)), 0.72)
                self._bar_targets[i] = self.BAR_MIN_H + span * shaped
            return

        if self._status in {"transcribing", "cleaning"}:
            active = self._tick % self.BAR_COUNT
            for i in range(self.BAR_COUNT):
                distance = min(abs(i - active), self.BAR_COUNT - abs(i - active))
                self._bar_targets[i] = max(self.BAR_MIN_H, self.BAR_MAX_H - distance * 4)
            return

        if self._status == "loading model":
            for i in range(self.BAR_COUNT):
                phase = math.sin((self._tick * 0.24) + i * 0.45) * 0.5 + 0.5
                self._bar_targets[i] = self.BAR_MIN_H + (self.BAR_MAX_H - self.BAR_MIN_H) * phase * 0.55
            return

        self._bar_targets = [float(self.BAR_MIN_H)] * self.BAR_COUNT

    def _step_bars(self) -> None:
        for i in range(self.BAR_COUNT):
            target = self._bar_targets[i]
            current = self._bar_heights[i]
            # Faster attack, gentler release makes speech feel responsive but
            # avoids jitter between adjacent microphone callbacks.
            factor = 0.62 if target > current else 0.34
            self._bar_heights[i] += (target - current) * factor

    def _draw(self) -> None:
        if not self._canvas:
            return

        canvas = self._canvas
        canvas.delete("all")
        compact = self._status in {"idle", "ready"}
        width = self.PILL_W_IDLE if compact else self.PILL_W_ACTIVE
        outline, accent = self._PALETTE.get(self._status, self._PALETTE["idle"])

        # Minimal capsule: no badge and no logo.
        canvas.create_polygon(
            self._pill_points(2, 2, width - 2, self.PILL_H - 2, 20),
            smooth=True,
            splinesteps=32,
            fill="#0b0f14",
            outline=outline,
            width=2 if self._status == "recording" else 1,
        )

        if compact:
            # A quiet center pulse is enough to show the background utility is alive.
            pulse = 3 if self._status == "idle" else 5
            canvas.create_oval(
                width // 2 - pulse,
                self.WAVE_Y - pulse,
                width // 2 + pulse,
                self.WAVE_Y + pulse,
                fill=accent,
                outline="",
            )
            return

        if self._status in {"transcribing", "cleaning"}:
            self._draw_processing_dots(canvas, accent)
        else:
            self._draw_waveform(canvas, accent)

    def _draw_waveform(self, canvas: tk.Canvas, color: str) -> None:
        for i, height in enumerate(self._bar_heights):
            x = self.WAVE_X0 + i * self.BAR_GAP
            half = max(1, int(height) // 2)
            canvas.create_rectangle(
                x,
                self.WAVE_Y - half,
                x + self.BAR_W,
                self.WAVE_Y + half,
                fill=color,
                outline="",
            )

    def _draw_processing_dots(self, canvas: tk.Canvas, color: str) -> None:
        spacing = 24
        total_width = (self.DOT_COUNT - 1) * spacing
        x0 = (self.PILL_W_ACTIVE - total_width) // 2
        for i in range(self.DOT_COUNT):
            phase = math.sin((self._tick * 0.38) - i * 0.9) * 0.5 + 0.5
            offset = int(phase * 6)
            x = x0 + i * spacing
            r = self.DOT_R
            canvas.create_oval(
                x - r,
                self.WAVE_Y - r - offset,
                x + r,
                self.WAVE_Y + r - offset,
                fill=color,
                outline="",
            )

    @staticmethod
    def _pill_points(x1: int, y1: int, x2: int, y2: int, r: int) -> list[int]:
        r = min(r, (y2 - y1) // 2, (x2 - x1) // 2)
        return [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]

    def _start_drag(self, event: tk.Event) -> None:
        self._drag_start = (event.x_root, event.y_root)

    def _drag(self, event: tk.Event) -> None:
        if not self._root or not self._drag_start:
            return
        start_x, start_y = self._drag_start
        x = self._root.winfo_x() + event.x_root - start_x
        y = self._root.winfo_y() + event.y_root - start_y
        self._root.geometry(f"+{x}+{y}")
        self._drag_start = (event.x_root, event.y_root)

    def _end_drag(self, event: tk.Event) -> None:
        if self._root:
            self.on_moved(self._root.winfo_x(), self._root.winfo_y())
        self._drag_start = None

    def _show_menu(self, event: tk.Event) -> None:
        if self._menu:
            self._menu.tk_popup(event.x_root, event.y_root)


class TrayApp:
    def __init__(
        self,
        get_status: Callable[[], str],
        get_last_error: Callable[[], str],
        get_settings: Callable[[], Settings],
        on_open_settings: Callable[[], None],
        on_retry: Callable[[], None],
        on_clear_history: Callable[[], None],
        on_toggle_cleanup: Callable[[], None],
        on_toggle_startup: Callable[[], None],
        on_toggle_sound: Callable[[], None],
        on_preload_model: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self.get_status = get_status
        self.get_last_error = get_last_error
        self.get_settings = get_settings
        self.on_open_settings = on_open_settings
        self.on_retry = on_retry
        self.on_clear_history = on_clear_history
        self.on_toggle_cleanup = on_toggle_cleanup
        self.on_toggle_startup = on_toggle_startup
        self.on_toggle_sound = on_toggle_sound
        self.on_preload_model = on_preload_model
        self.on_quit = on_quit
        self.icon = pystray.Icon("Voice Prompt", self._image(), "Voice Prompt", self._menu())

    def run_detached(self) -> None:
        self.icon.run_detached()

    def stop(self) -> None:
        self.icon.stop()

    def refresh(self) -> None:
        if getattr(self.icon, "visible", False):
            self.icon.menu = self._menu()
            try:
                self.icon.update_menu()
            except Exception:
                pass

    def _menu(self) -> pystray.Menu:
        settings = self.get_settings()
        items = [
            pystray.MenuItem(f"Status: {self.get_status()}", None, enabled=False),
            pystray.MenuItem("Open settings", lambda icon, item: self.on_open_settings()),
            pystray.MenuItem("Warm up model", lambda icon, item: self.on_preload_model()),
            pystray.MenuItem("Retry last transcription", lambda icon, item: self.on_retry()),
            pystray.MenuItem("Clear local history", lambda icon, item: self.on_clear_history(), enabled=settings.save_history),
            pystray.MenuItem("Sound feedback", lambda icon, item: self.on_toggle_sound(), checked=lambda item: settings.sound_feedback),
            pystray.MenuItem("Cloud cleanup", lambda icon, item: self.on_toggle_cleanup(), checked=lambda item: settings.cleanup_provider != "none"),
            pystray.MenuItem("Start on boot", lambda icon, item: self.on_toggle_startup(), checked=lambda item: settings.startup_on_boot),
        ]
        if self.get_last_error():
            items.append(pystray.MenuItem(f"Last error: {self.get_last_error()}", None, enabled=False))
        items.extend([pystray.Menu.SEPARATOR, pystray.MenuItem("Quit", lambda icon, item: self.on_quit())])
        return pystray.Menu(*items)

    @staticmethod
    def _image() -> Image.Image:
        # Minimal waveform tray identity; no product logo/badge.
        image = Image.new("RGB", (64, 64), "#0b0f14")
        draw = ImageDraw.Draw(image)
        heights = [12, 22, 34, 46, 30, 18, 38, 26, 14]
        x = 8
        for height in heights:
            y0 = (64 - height) // 2
            draw.rounded_rectangle((x, y0, x + 3, y0 + height), radius=1, fill="#22c55e")
            x += 6
        return image


class SettingsWindow:
    def __init__(self, settings: Settings, on_save: Callable[[Settings], None]) -> None:
        self.settings = settings
        self.on_save = on_save
        self._window: tk.Toplevel | None = None

    @property
    def is_open(self) -> bool:
        return bool(self._window and self._window.winfo_exists())

    def focus(self) -> None:
        if self.is_open and self._window:
            self._window.lift()
            self._window.focus_force()

    def show(self, parent: tk.Misc) -> None:
        root = tk.Toplevel(parent)
        self._window = root
        root.title("Voice Prompt Settings")
        root.resizable(False, False)
        root.attributes("-topmost", True)
        root.protocol("WM_DELETE_WINDOW", root.destroy)

        hotkey = tk.StringVar(value=self.settings.hotkey)
        backend = tk.StringVar(value=self.settings.asr_backend)
        model = tk.StringVar(value=self.settings.model)
        language = tk.StringVar(value=self.settings.language or "auto")
        beam_size = tk.IntVar(value=self.settings.beam_size)
        recording_mode = tk.StringVar(value=self.settings.recording_mode)
        input_device = tk.StringVar(value=self.settings.input_device)
        max_recording = tk.DoubleVar(value=self.settings.max_recording_seconds)
        sound_feedback = tk.BooleanVar(value=self.settings.sound_feedback)
        startup = tk.BooleanVar(value=self.settings.startup_on_boot)
        preload = tk.BooleanVar(value=self.settings.preload_model)
        vad = tk.BooleanVar(value=self.settings.vad_filter)
        save_history = tk.BooleanVar(value=self.settings.save_history)
        cleanup_provider = tk.StringVar(value=self.settings.cleanup_provider)
        cloud_model = tk.StringVar(
            value=self.settings.gemini_model
            if self.settings.cleanup_provider == "gemini"
            else self.settings.openrouter_model
        )
        cleanup_timeout = tk.DoubleVar(value=self.settings.cleanup_timeout_seconds)
        preserve_clipboard = tk.BooleanVar(value=self.settings.preserve_clipboard)
        restore_focus = tk.BooleanVar(value=self.settings.restore_focus_on_paste)
        cpp_exe = tk.StringVar(value=self.settings.whisper_cpp_executable)
        cpp_model = tk.StringVar(value=self.settings.whisper_cpp_model)
        cpp_threads = tk.IntVar(value=self.settings.whisper_cpp_threads)

        def update_cloud_model(*_args: object) -> None:
            provider = cleanup_provider.get()
            if provider == "gemini" and cloud_model.get() == self.settings.openrouter_model:
                cloud_model.set(self.settings.gemini_model)
            elif provider == "openrouter" and cloud_model.get() == self.settings.gemini_model:
                cloud_model.set(self.settings.openrouter_model)

        cleanup_provider.trace_add("write", update_cloud_model)

        frame = ttk.Frame(root, padding=14)
        frame.grid(row=0, column=0, sticky="nsew")
        self._combo(frame, "Hotkey", hotkey, HOTKEYS, 0)
        self._combo(frame, "Mode", recording_mode, RECORDING_MODES, 1)
        self._combo(frame, "ASR backend", backend, ASR_BACKENDS, 2)
        self._combo(frame, "Model", model, MODELS, 3)
        self._combo(frame, "Language", language, LANGUAGES, 4)
        self._spin(frame, "Accuracy", beam_size, 1, 5, 5)
        self._entry(frame, "Input device", input_device, 6)
        self._spin(frame, "Max recording (s)", max_recording, 3, 300, 7)
        self._entry(frame, "whisper.cpp exe", cpp_exe, 8)
        self._entry(frame, "whisper.cpp model", cpp_model, 9)
        self._spin(frame, "whisper.cpp threads", cpp_threads, 1, 32, 10)
        ttk.Checkbutton(frame, text="Play sound when recording starts/stops", variable=sound_feedback).grid(row=11, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(frame, text="Warm up model at startup", variable=preload).grid(row=12, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(frame, text="Filter silence (recommended)", variable=vad).grid(row=13, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(frame, text="Preserve clipboard after paste", variable=preserve_clipboard).grid(row=14, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(frame, text="Return focus to original dictation window", variable=restore_focus).grid(row=15, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(frame, text="Save transcription history locally", variable=save_history).grid(row=16, column=0, columnspan=2, sticky="w")
        self._combo(frame, "Cloud cleanup", cleanup_provider, CLEANUP_PROVIDERS, 17)
        self._entry(frame, "Cloud model", cloud_model, 18)
        self._spin(frame, "Cloud timeout (s)", cleanup_timeout, 1, 15, 19)
        ttk.Checkbutton(frame, text="Start on boot", variable=startup).grid(row=20, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Dictionary replacements").grid(row=21, column=0, columnspan=2, sticky="w", pady=(10, 2))

        replacements = tk.Text(frame, width=48, height=7)
        replacements.grid(row=22, column=0, columnspan=2, sticky="ew")
        replacements.insert("1.0", "\n".join(f"{source}={target}" for source, target in self.settings.replacements.items()))

        buttons = ttk.Frame(frame)
        buttons.grid(row=23, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=root.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(
            buttons,
            text="Save",
            command=lambda: self._save(
                root,
                hotkey.get(), recording_mode.get(), backend.get(), model.get(), language.get(), beam_size.get(),
                input_device.get(), max_recording.get(), cpp_exe.get(), cpp_model.get(), cpp_threads.get(),
                sound_feedback.get(), preload.get(), vad.get(), startup.get(), cleanup_provider.get(), cloud_model.get(),
                cleanup_timeout.get(), preserve_clipboard.get(), restore_focus.get(), save_history.get(),
                replacements.get("1.0", "end"),
            ),
        ).grid(row=0, column=1)

    @staticmethod
    def _combo(parent: ttk.Frame, label: str, variable: tk.StringVar, values: list[str], row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 12))
        ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=30).grid(row=row, column=1, sticky="ew", pady=2)

    @staticmethod
    def _entry(parent: ttk.Frame, label: str, variable: tk.StringVar, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 12))
        ttk.Entry(parent, textvariable=variable, width=34).grid(row=row, column=1, sticky="ew", pady=2)

    @staticmethod
    def _spin(parent: ttk.Frame, label: str, variable: tk.Variable, low: float, high: float, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 12))
        ttk.Spinbox(parent, from_=low, to=high, textvariable=variable, width=30).grid(row=row, column=1, sticky="ew", pady=2)

    def _save(
        self,
        root: tk.Toplevel,
        hotkey: str,
        recording_mode: str,
        backend: str,
        model: str,
        language: str,
        beam_size: int,
        input_device: str,
        max_recording: float,
        cpp_exe: str,
        cpp_model: str,
        cpp_threads: int,
        sound_feedback: bool,
        preload: bool,
        vad: bool,
        startup: bool,
        cleanup_provider: str,
        cloud_model: str,
        cleanup_timeout: float,
        preserve_clipboard: bool,
        restore_focus: bool,
        save_history: bool,
        replacements_text: str,
    ) -> None:
        replacements: dict[str, str] = {}
        for line in replacements_text.splitlines():
            if not line.strip():
                continue
            if "=" not in line:
                messagebox.showerror("Voice Prompt", f"Replacement must use source=target:\n{line}", parent=root)
                return
            source, target = line.split("=", 1)
            source, target = source.strip(), target.strip()
            if source and target:
                replacements[source] = target

        provider = cleanup_provider if cleanup_provider in CLEANUP_PROVIDERS else "none"
        model_updates = (
            {"gemini_model": cloud_model.strip() or "gemini-2.5-flash-lite"}
            if provider == "gemini"
            else {"openrouter_model": cloud_model.strip() or "openrouter/free"}
        )
        updated = replace(
            self.settings,
            hotkey=hotkey,
            recording_mode=recording_mode,
            asr_backend=backend,
            model=model,
            language="" if language == "auto" else language,
            beam_size=max(1, min(5, int(beam_size))),
            input_device=input_device.strip(),
            max_recording_seconds=max(3.0, min(300.0, float(max_recording))),
            whisper_cpp_executable=cpp_exe.strip(),
            whisper_cpp_model=cpp_model.strip(),
            whisper_cpp_threads=max(1, min(32, int(cpp_threads))),
            sound_feedback=bool(sound_feedback),
            preload_model=preload,
            vad_filter=vad,
            startup_on_boot=startup,
            cleanup_provider=provider,
            cleanup_timeout_seconds=max(1.0, min(15.0, float(cleanup_timeout))),
            preserve_clipboard=preserve_clipboard,
            restore_focus_on_paste=restore_focus,
            save_history=save_history,
            replacements=replacements,
            **model_updates,
        )
        self.on_save(updated)
        root.destroy()
