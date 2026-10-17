from __future__ import annotations

import tkinter as tk
import unittest
from tkinter import ttk
from unittest.mock import patch

from voiceprompt.config import Settings
from voiceprompt.settings_ui import SettingsWindow


class SettingsUITests(unittest.TestCase):
    def test_settings_use_own_tcl_variables_with_floating_pill_root_present(self):
        try:
            primary = tk.Tk()
            primary.withdraw()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.addCleanup(primary.destroy)
        saved = []
        window = SettingsWindow(Settings(), saved.append)

        def visit(widget):
            yield widget
            for child in widget.winfo_children():
                yield from visit(child)

        def inspect(root):
            root.update_idletasks()
            widgets = list(visit(root))
            notebook = next(w for w in widgets if isinstance(w, ttk.Notebook))
            self.assertEqual([notebook.tab(t, "text") for t in notebook.tabs()], ["Dictation", "Microphone", "Dictionary", "Cleanup"])
            self.assertLess(root.winfo_reqheight(), root.winfo_screenheight())
            combos = [w for w in widgets if isinstance(w, ttk.Combobox)]
            self.assertEqual(combos[0].get(), "right_ctrl")
            # Changing a control in this interpreter must be reflected in saved settings.
            engine = next(w for w in combos if tuple(w["values"]) == ("whisper", "nemotron", "parakeet", "moonshine"))
            engine.set("nemotron")
            sound_toggle = next(w for w in widgets if isinstance(w, ttk.Checkbutton) and w["text"] == "Play gentle recording sounds")
            sound_toggle.invoke()
            next(w for w in combos if tuple(w["values"]) == ("vulkan", "cpu")).set("cpu")
            next(w for w in widgets if isinstance(w, ttk.Button) and w["text"] == "Save").invoke()

        with patch.object(tk.Tk, "mainloop", inspect), patch("voiceprompt.settings_ui.microphones", return_value=["Test microphone"]):
            window.show()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].backend, "nemotron")
        self.assertEqual(saved[0].nemotron_device, "cpu")
        self.assertEqual(saved[0].model, "base.en")
        self.assertFalse(saved[0].noise_suppression)
        self.assertFalse(saved[0].sound_feedback)
