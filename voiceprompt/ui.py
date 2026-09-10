from __future__ import annotations

import math
import queue
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import replace
from tkinter import messagebox, ttk

import pystray
from PIL import Image, ImageDraw

from voiceprompt.config import Settings


HOTKEYS = ["right_ctrl", "left_ctrl", "right_alt", "left_alt", "f8", "f9"]
MODELS = [
    "Systran/faster-distil-whisper-small.en",
    "base.en",
    "small.en",
    "small",
    "tiny.en",
    "tiny",
    "base",
]
LANGUAGES = ["en", "auto"]
RECORDING_MODES = ["ptt", "toggle"]
CLEANUP_PROVIDERS = ["none", "openrouter", "gemini"]


class FloatingPill:
    # Pill dimensions
    PILL_W_IDLE = 64       # collapsed (just badge)
    PILL_H = 56            # fixed height
    PILL_W_ACTIVE = 280    # expanded (badge + waveform)

    # Badge
    BADGE_R = 22           # radius of the circular badge
    BADGE_CX = 32          # centre-x of badge (same in both sizes)
    BADGE_CY = 28          # centre-y

    # Waveform area starts after badge
    WAVE_X0 = 68           # left edge of bars
    WAVE_Y = 28            # vertical centre

    # Bar config
    BAR_COUNT = 18
    BAR_W = 3
    BAR_GAP = 5            # spacing between bar left edges
    BAR_MIN_H = 4
    BAR_MAX_H = 28

    # Dot config (processing state)
    DOT_COUNT = 4
    DOT_R = 5

    # State palette: (badge_fill, badge_glow, bar_color)
    _PALETTE: dict[str, tuple[str, str, str]] = {
        "idle":          ("#1a1f2e", "#374151", "#4b5563"),
        "ready":         ("#0d2818", "#22c55e", "#22c55e"),
        "recording":     ("#1a0d0d", "#22c55e", "#22c55e"),   # green waveform when active
        "transcribing":  ("#071a26", "#0ea5e9", "#0ea5e9"),
        "cleaning":      ("#1a0d26", "#a78bfa", "#a78bfa"),
        "loading model": ("#1a1200", "#f59e0b", "#f59e0b"),
        "error":         ("#1a0808", "#ef4444", "#ef4444"),
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
        # per-bar heights for organic waveform
        self._bar_heights = [self.BAR_MIN_H] * self.BAR_COUNT
        self._bar_targets = [self.BAR_MIN_H] * self.BAR_COUNT

    # ------------------------------------------------------------------ run / stop

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

        w = self.PILL_W_IDLE
        h = self.PILL_H
        x = settings.pill_position_x if settings.pill_position_x >= 0 else 90
        y = settings.pill_position_y if settings.pill_position_y >= 0 else 520
        root.geometry(f"{w}x{h}+{x}+{y}")

        canvas = tk.Canvas(root, width=w, height=h, bg="#ff00ff", highlightthickness=0, bd=0)
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

    # ------------------------------------------------------------------ event loop

    def _poll(self) -> None:
        while True:
            try:
                name, payload = self._events.get_nowait()
            except queue.Empty:
                break
            if name == "status":
                old = self._status
                self._status = str(payload)
                if old != self._status:
                    self._resize_pill()
                self._draw()
            elif name == "stop" and self._root:
                self._root.destroy()
                return
        if self._root:
            self._root.after(80, self._poll)

    def _animate(self) -> None:
        self._tick += 1
        active = self._status not in {"idle"}
        if active:
            self._update_bar_targets()
            self._step_bars()
            self._draw()
        if self._root:
            self._root.after(50, self._animate)   # ~20 fps smooth enough for tkinter

    def _resize_pill(self) -> None:
        if not self._root or not self._canvas:
            return
        is_idle = self._status == "idle"
        w = self.PILL_W_IDLE if is_idle else self.PILL_W_ACTIVE
        h = self.PILL_H
        x = self._root.winfo_x()
        y = self._root.winfo_y()
        self._root.geometry(f"{w}x{h}+{x}+{y}")
        self._canvas.config(width=w, height=h)

    # ------------------------------------------------------------------ bar physics

    def _update_bar_targets(self) -> None:
        import random
        status = self._status
        if status == "recording":
            # random organic heights simulating voice input
            for i in range(self.BAR_COUNT):
                phase = math.sin((self._tick * 0.4) + i * 0.9) * 0.5 + 0.5
                noise = random.uniform(0.0, 0.3)
                self._bar_targets[i] = int(self.BAR_MIN_H + (self.BAR_MAX_H - self.BAR_MIN_H) * (phase + noise))
        elif status in {"transcribing", "cleaning"}:
            # scanning pattern
            active = self._tick % self.BAR_COUNT
            for i in range(self.BAR_COUNT):
                dist = min(abs(i - active), self.BAR_COUNT - abs(i - active))
                h = self.BAR_MAX_H - dist * 3
                self._bar_targets[i] = max(self.BAR_MIN_H, h)
        elif status == "loading model":
            # gentle pulse
            for i in range(self.BAR_COUNT):
                phase = math.sin((self._tick * 0.3) + i * 0.5) * 0.5 + 0.5
                self._bar_targets[i] = int(self.BAR_MIN_H + (self.BAR_MAX_H - self.BAR_MIN_H) * phase * 0.6)
        else:
            for i in range(self.BAR_COUNT):
                self._bar_targets[i] = self.BAR_MIN_H

    def _step_bars(self) -> None:
        for i in range(self.BAR_COUNT):
            diff = self._bar_targets[i] - self._bar_heights[i]
            self._bar_heights[i] += diff * 0.35   # easing factor

    # ------------------------------------------------------------------ drawing

    def _draw(self) -> None:
        if not self._canvas or not self._root:
            return
        canvas = self._canvas
        canvas.delete("all")

        is_idle = self._status == "idle"
        w = self.PILL_W_IDLE if is_idle else self.PILL_W_ACTIVE
        h = self.PILL_H
        palette = self._PALETTE.get(self._status, self._PALETTE["idle"])
        badge_fill, glow_color, bar_color = palette

        # --- outer pill body ---
        self._draw_pill_body(canvas, w, h, glow_color, is_idle)

        # --- badge circle ---
        cx, cy = self.BADGE_CX, self.BADGE_CY
        r = self.BADGE_R
        # glow ring (outer)
        canvas.create_oval(cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4,
                           fill="", outline=glow_color, width=2)
        # badge fill
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                           fill=badge_fill, outline=glow_color, width=1)
        # bolt icon
        self._draw_bolt(canvas, cx, cy, glow_color)

        # --- waveform / dots (only when not idle) ---
        if not is_idle:
            if self._status in {"loading model", "transcribing"} and self._tick % 20 < 10:
                # dots for processing-feel states
                self._draw_dots(canvas, bar_color)
            else:
                self._draw_waveform(canvas, bar_color)

    def _draw_pill_body(self, canvas: tk.Canvas, w: int, h: int, glow: str, is_idle: bool) -> None:
        # outer glow shadow layer
        canvas.create_polygon(
            self._pill_points(4, 4, w - 4, h - 4, (h - 8) // 2),
            smooth=True, splinesteps=32,
            fill="", outline=glow, width=1,
        )
        # main dark body
        canvas.create_polygon(
            self._pill_points(8, 6, w - 8, h - 6, (h - 12) // 2),
            smooth=True, splinesteps=32,
            fill="#0d1117", outline="#1e2533", width=1,
        )
        # subtle inner highlight (top edge only — glassmorphism sheen)
        canvas.create_polygon(
            self._pill_points(10, 7, w - 10, 7 + 10, (10) // 2),
            smooth=True, splinesteps=16,
            fill="#1e2533", outline="",
        )

    def _draw_bolt(self, canvas: tk.Canvas, cx: int, cy: int, color: str) -> None:
        # lightning bolt polygon
        canvas.create_polygon(
            cx + 2,  cy - 12,
            cx - 4,  cy - 1,
            cx + 1,  cy - 1,
            cx - 3,  cy + 12,
            cx + 6,  cy + 0,
            cx + 1,  cy + 0,
            fill=color, outline="", smooth=False,
        )

    def _draw_waveform(self, canvas: tk.Canvas, color: str) -> None:
        x0 = self.WAVE_X0
        cy = self.WAVE_Y
        for i, h in enumerate(self._bar_heights):
            x = x0 + i * self.BAR_GAP
            half = int(h) // 2
            # subtle glow (wider, semi-transparent approximation via lighter color)
            canvas.create_rectangle(x - 1, cy - half - 1, x + self.BAR_W + 1, cy + half + 1,
                                    fill=self._dim_color(color, 0.25), outline="")
            # main bar
            canvas.create_rectangle(x, cy - half, x + self.BAR_W, cy + half,
                                    fill=color, outline="")

    def _draw_dots(self, canvas: tk.Canvas, color: str) -> None:
        """Bouncing dots for processing states."""
        total_w = (self.DOT_COUNT - 1) * 28
        x0 = self.WAVE_X0 + (self.PILL_W_ACTIVE - self.WAVE_X0 - total_w) // 2
        cy = self.WAVE_Y
        for i in range(self.DOT_COUNT):
            phase = math.sin((self._tick * 0.4) - i * 1.0) * 0.5 + 0.5
            offset = int(phase * 8)
            x = x0 + i * 28
            r = self.DOT_R
            canvas.create_oval(x - r, cy - r - offset, x + r, cy + r - offset,
                               fill=color, outline="")

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _pill_points(x1: int, y1: int, x2: int, y2: int, r: int) -> list[int]:
        """Return polygon points for a horizontally-oriented pill shape."""
        r = min(r, (y2 - y1) // 2, (x2 - x1) // 2)
        return [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]

    @staticmethod
    def _dim_color(hex_color: str, alpha: float) -> str:
        """Blend hex_color toward black by alpha factor (cheap glow approximation)."""
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        r = int(r * alpha)
        g = int(g * alpha)
        b = int(b * alpha)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _start_drag(self, event: tk.Event) -> None:
        self._drag_start = (event.x_root, event.y_root)

    def _drag(self, event: tk.Event) -> None:
        if not self._root or not self._drag_start:
            return
        start_x, start_y = self._drag_start
        dx = event.x_root - start_x
        dy = event.y_root - start_y
        x = self._root.winfo_x() + dx
        y = self._root.winfo_y() + dy
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
        on_settings_saved: Callable[[Settings], None],
        on_retry: Callable[[], None],
        on_toggle_cleanup: Callable[[], None],
        on_toggle_startup: Callable[[], None],
        on_preload_model: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self.get_status = get_status
        self.get_last_error = get_last_error
        self.get_settings = get_settings
        self.on_settings_saved = on_settings_saved
        self.on_retry = on_retry
        self.on_toggle_cleanup = on_toggle_cleanup
        self.on_toggle_startup = on_toggle_startup
        self.on_preload_model = on_preload_model
        self.on_quit = on_quit
        self.icon = pystray.Icon("Voice Prompt", self._image(), "Voice Prompt", self._menu())
        self._settings_open = False

    def run(self) -> None:
        self.icon.run()

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
        last_error = self.get_last_error()
        error_item = pystray.MenuItem(f"Last error: {last_error}", None, enabled=False)
        items = [
            pystray.MenuItem(f"Status: {self.get_status()}", None, enabled=False),
            pystray.MenuItem("Open settings", lambda icon, item: self.open_settings()),
            pystray.MenuItem("Warm up model", lambda icon, item: self.on_preload_model()),
            pystray.MenuItem("Retry last transcription", lambda icon, item: self.on_retry()),
            pystray.MenuItem(
                "Cloud cleanup",
                lambda icon, item: self.on_toggle_cleanup(),
                checked=lambda item: settings.cleanup_provider != "none",
            ),
            pystray.MenuItem(
                "Start on boot",
                lambda icon, item: self.on_toggle_startup(),
                checked=lambda item: settings.startup_on_boot,
            ),
        ]
        if last_error:
            items.append(error_item)
        items.extend([pystray.Menu.SEPARATOR, pystray.MenuItem("Quit", lambda icon, item: self.on_quit())])
        return pystray.Menu(*items)

    def open_settings(self) -> None:
        if self._settings_open:
            return
        self._settings_open = True

        def run_window() -> None:
            try:
                SettingsWindow(self.get_settings(), self.on_settings_saved).show()
            finally:
                self._settings_open = False

        threading.Thread(target=run_window, daemon=True).start()

    @staticmethod
    def _image() -> Image.Image:
        image = Image.new("RGB", (64, 64), "#111827")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((14, 8, 50, 42), radius=16, fill="#22c55e")
        draw.rectangle((29, 39, 35, 52), fill="#22c55e")
        draw.rounded_rectangle((22, 50, 42, 56), radius=3, fill="#22c55e")
        return image


class SettingsWindow:
    def __init__(self, settings: Settings, on_save: Callable[[Settings], None]) -> None:
        self.settings = settings
        self.on_save = on_save

    def show(self) -> None:
        root = tk.Tk()
        root.title("Voice Prompt Settings")
        root.resizable(False, False)
        root.attributes("-topmost", True)
        root.protocol("WM_DELETE_WINDOW", root.destroy)

        hotkey = tk.StringVar(value=self.settings.hotkey)
        model = tk.StringVar(value=self.settings.model)
        language = tk.StringVar(value=self.settings.language or "en")
        beam_size = tk.IntVar(value=self.settings.beam_size)
        recording_mode = tk.StringVar(value=self.settings.recording_mode)
        startup = tk.BooleanVar(value=self.settings.startup_on_boot)
        preload_model = tk.BooleanVar(value=self.settings.preload_model)
        vad_filter = tk.BooleanVar(value=self.settings.vad_filter)
        cleanup_provider = tk.StringVar(value=self.settings.cleanup_provider)
        cloud_model = tk.StringVar(
            value=self.settings.gemini_model
            if self.settings.cleanup_provider == "gemini"
            else self.settings.openrouter_model
        )
        cleanup_timeout = tk.DoubleVar(value=self.settings.cleanup_timeout_seconds)
        preserve_clipboard = tk.BooleanVar(value=self.settings.preserve_clipboard)

        def update_cloud_model(*_args: object) -> None:
            if cleanup_provider.get() == "gemini" and cloud_model.get() == self.settings.openrouter_model:
                cloud_model.set(self.settings.gemini_model)
            elif cleanup_provider.get() == "openrouter" and cloud_model.get() == self.settings.gemini_model:
                cloud_model.set(self.settings.openrouter_model)

        cleanup_provider.trace_add("write", update_cloud_model)

        frame = ttk.Frame(root, padding=14)
        frame.grid(row=0, column=0, sticky="nsew")

        self._combo(frame, "Hotkey", hotkey, HOTKEYS, 0)
        self._combo(frame, "Mode", recording_mode, RECORDING_MODES, 1)
        self._combo(frame, "Model", model, MODELS, 2)
        self._combo(frame, "Language", language, LANGUAGES, 3)
        ttk.Label(frame, text="Accuracy").grid(row=4, column=0, sticky="w", pady=3, padx=(0, 12))
        ttk.Spinbox(frame, from_=1, to=5, textvariable=beam_size, width=18).grid(
            row=4, column=1, sticky="ew", pady=3
        )

        ttk.Checkbutton(frame, text="Warm up model at startup", variable=preload_model).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(frame, text="Filter silence (recommended)", variable=vad_filter).grid(
            row=6, column=0, columnspan=2, sticky="w"
        )
        ttk.Checkbutton(frame, text="Preserve clipboard after paste", variable=preserve_clipboard).grid(
            row=7, column=0, columnspan=2, sticky="w"
        )
        self._combo(frame, "Cloud cleanup", cleanup_provider, CLEANUP_PROVIDERS, 8)
        ttk.Label(frame, text="Cloud model").grid(row=9, column=0, sticky="w", pady=3, padx=(0, 12))
        ttk.Entry(frame, textvariable=cloud_model, width=24).grid(row=9, column=1, sticky="ew", pady=3)
        ttk.Label(frame, text="Cloud timeout (s)").grid(row=10, column=0, sticky="w", pady=3, padx=(0, 12))
        ttk.Spinbox(frame, from_=1, to=15, increment=0.5, textvariable=cleanup_timeout, width=18).grid(
            row=10, column=1, sticky="ew", pady=3
        )
        ttk.Checkbutton(frame, text="Start on boot", variable=startup).grid(
            row=11, column=0, columnspan=2, sticky="w"
        )

        ttk.Label(frame, text="Dictionary replacements").grid(
            row=12, column=0, columnspan=2, sticky="w", pady=(12, 2)
        )
        replacements = tk.Text(frame, width=44, height=8)
        replacements.grid(row=13, column=0, columnspan=2, sticky="ew")
        replacements.insert(
            "1.0",
            "\n".join(f"{source}={target}" for source, target in self.settings.replacements.items()),
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=14, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=root.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(
            buttons,
            text="Save",
            command=lambda: self._save(
                root,
                hotkey.get(),
                recording_mode.get(),
                model.get(),
                language.get(),
                beam_size.get(),
                preload_model.get(),
                vad_filter.get(),
                startup.get(),
                cleanup_provider.get(),
                cloud_model.get(),
                cleanup_timeout.get(),
                preserve_clipboard.get(),
                replacements.get("1.0", "end"),
            ),
        ).grid(row=0, column=1)

        root.mainloop()

    @staticmethod
    def _combo(parent: ttk.Frame, label: str, variable: tk.StringVar, values: list[str], row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3, padx=(0, 12))
        ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=20).grid(
            row=row, column=1, sticky="ew", pady=3
        )

    def _save(
        self,
        root: tk.Tk,
        hotkey: str,
        recording_mode: str,
        model: str,
        language: str,
        beam_size: int,
        preload_model: bool,
        vad_filter: bool,
        startup: bool,
        cleanup_provider: str,
        cloud_model: str,
        cleanup_timeout: float,
        preserve_clipboard: bool,
        replacements_text: str,
    ) -> None:
        replacements: dict[str, str] = {}
        for line in replacements_text.splitlines():
            if not line.strip():
                continue
            if "=" not in line:
                messagebox.showerror("Voice Prompt", f"Replacement must use source=target:\n{line}")
                return
            source, target = line.split("=", 1)
            replacements[source.strip()] = target.strip()

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
            model=model,
            language="" if language == "auto" else language,
            beam_size=max(1, min(5, int(beam_size))),
            preload_model=preload_model,
            vad_filter=vad_filter,
            startup_on_boot=startup,
            cleanup_provider=provider,
            cleanup_timeout_seconds=max(1.0, min(15.0, float(cleanup_timeout))),
            preserve_clipboard=preserve_clipboard,
            replacements=replacements,
            **model_updates,
        )
        self.on_save(updated)
        root.destroy()
