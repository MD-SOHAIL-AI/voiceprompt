from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import replace
from tkinter import messagebox, ttk

from voiceprompt.config import Settings
from voiceprompt.recorder import microphones
from voiceprompt.theme import BACKGROUND, INK, LINE, SURFACE, ScrollablePage, fit_window, install_theme, pixels


class SettingsWindow:
    def __init__(self, settings: Settings, on_save: Callable[[Settings], None]) -> None:
        self.settings = settings
        self.on_save = on_save

    def show(self) -> None:
        root = tk.Tk()
        install_theme(root)
        root.title("VoicePrompt Settings")
        fit_window(root, 720, 740, minimum=(600, 480))
        root.attributes("-topmost", True)
        frame = ttk.Frame(root, padding=pixels(root, 24))
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Make it yours", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Dictation, microphone, and text preferences.", style="Muted.TLabel").pack(anchor="w", pady=(pixels(root, 5), pixels(root, 20)))
        notebook = ttk.Notebook(frame)
        notebook.pack(fill="both", expand=True)
        pages = {}
        for name in ("Dictation", "Microphone", "Dictionary"):
            page = ScrollablePage(notebook, padding=pixels(root, 14))
            notebook.add(page, text=name)
            pages[name] = page.body
            page.body.columnconfigure(1, weight=1)
        values = {}
        for name in (
            "hotkey", "recording_mode", "backend", "model", "streaming_model", "language",
            "microphone", "capture_mode",
            "nemotron_device",
        ):
            values[name] = tk.StringVar(master=root, value=getattr(self.settings, name))
        values["language"].set(self.settings.language or "auto")
        for name in ("beam_size", "cpu_threads"):
            values[name] = tk.IntVar(master=root, value=getattr(self.settings, name))
        for name in ("preload_model", "vad_filter", "preserve_clipboard", "startup_on_boot", "noise_suppression", "sound_feedback"):
            values[name] = tk.BooleanVar(master=root, value=getattr(self.settings, name))

        page = pages["Dictation"]
        self._combo(page, "Hotkey", values["hotkey"], ["right_ctrl", "left_ctrl", "right_alt", "left_alt", "f8", "f9"], 0)
        self._combo(page, "Recording mode", values["recording_mode"], ["ptt", "toggle"], 1)
        self._combo(page, "Speech engine", values["backend"], ["whisper", "nemotron", "parakeet", "moonshine"], 2)
        self._combo(page, "Nemotron processing", values["nemotron_device"], ["vulkan", "cpu"], 3)
        self._combo(page, "Whisper model", values["model"], ["base.en", "tiny.en", "small.en", "Systran/faster-distil-whisper-small.en", "small", "base", "tiny"], 4)
        self._combo(page, "Moonshine model", values["streaming_model"], ["tiny", "small"], 5)
        self._combo(page, "Whisper language", values["language"], ["en", "auto"], 6)
        self._spin(page, "Whisper beam size", values["beam_size"], 1, 5, 7)
        self._spin(page, "Whisper / Parakeet CPU threads", values["cpu_threads"], 1, 12, 8)
        ttk.Label(page, text="Nemotron keeps English sentence context while you speak.\nVulkan uses your graphics processor. Models download on first selection.", wraplength=440).grid(row=9, column=0, columnspan=2, sticky="w", pady=10)
        for row, name, label in (
            (10, "preload_model", "Warm up model at startup"),
            (11, "vad_filter", "Whisper: filter silence"),
            (12, "preserve_clipboard", "Preserve clipboard after paste"),
            (13, "startup_on_boot", "Start on boot"),
            (14, "sound_feedback", "Play gentle recording sounds"),
        ):
            ttk.Checkbutton(page, text=label, variable=values[name]).grid(row=row, column=0, columnspan=2, sticky="w")

        page = pages["Microphone"]
        try:
            inputs = microphones()
        except Exception:
            inputs = []
        inputs = list(dict.fromkeys(["", self.settings.microphone, *inputs]))
        self._combo(page, "Microphone", values["microphone"], inputs, 0)
        self._combo(page, "Capture mode", values["capture_mode"], ["auto", "wasapi", "mme"], 1)
        ttk.Label(page, text="An empty microphone follows the Windows default. Auto prefers WASAPI\nand reports any fallback in the tray menu.", wraplength=440).grid(row=2, column=0, columnspan=2, sticky="w", pady=10)
        ttk.Checkbutton(page, text="RNNoise suppression (optional)", variable=values["noise_suppression"]).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Label(page, text="Keep suppression off until your noisy-speech comparison shows better\nrecognition. It requires the optional noise dependencies.", wraplength=440).grid(row=4, column=0, columnspan=2, sticky="w", pady=10)

        page = pages["Dictionary"]
        ttk.Label(page, text="One source=target replacement per line. Replacements apply to final text.\nWhisper and Moonshine also use target names as recognition hints.", wraplength=440).pack(anchor="w", pady=(0, 8))
        replacements = tk.Text(page, width=55, height=12, font=("Segoe UI", 11), background=SURFACE,
                               foreground=INK, insertbackground=INK, relief="solid", borderwidth=1,
                               highlightthickness=1, highlightbackground=LINE, padx=12, pady=12, wrap="word")
        replacements.pack(fill="both", expand=True)
        replacements.insert("1.0", "\n".join(f"{k}={v}" for k, v in self.settings.replacements.items()))

        def save() -> None:
            try:
                updates = {key: variable.get() for key, variable in values.items()}
                updates["language"] = "" if updates["language"] == "auto" else updates["language"]
                updates["beam_size"] = max(1, min(5, int(updates["beam_size"])))
                updates["cpu_threads"] = max(1, min(12, int(updates["cpu_threads"])))
                pairs = {}
                for line in replacements.get("1.0", "end").splitlines():
                    if not line.strip():
                        continue
                    if "=" not in line:
                        raise ValueError(f"Replacement must use source=target: {line}")
                    source, target = (s.strip() for s in line.split("=", 1))
                    if not source or not target:
                        raise ValueError("Replacement source and target cannot be empty.")
                    pairs[source] = target
                self.on_save(replace(self.settings, replacements=pairs, **updates))
            except (ValueError, tk.TclError) as exc:
                messagebox.showerror("VoicePrompt", str(exc), parent=root)
                return
            root.destroy()

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=root.destroy).pack(side="left", padx=8)
        ttk.Button(buttons, text="Save", command=save, style="Primary.TButton").pack(side="left")
        root.mainloop()

    @staticmethod
    def _combo(parent, label, variable, choices, row) -> None:
        ttk.Label(parent, text=label, wraplength=pixels(parent, 190)).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 12))
        ttk.Combobox(parent, textvariable=variable, values=choices, state="readonly", width=28).grid(row=row, column=1, sticky="ew", pady=4)

    @staticmethod
    def _spin(parent, label, variable, minimum, maximum, row) -> None:
        ttk.Label(parent, text=label, wraplength=pixels(parent, 190)).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 12))
        ttk.Spinbox(parent, from_=minimum, to=maximum, textvariable=variable, width=12).grid(row=row, column=1, sticky="ew", pady=4)
