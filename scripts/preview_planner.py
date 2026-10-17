"""Open an isolated Planner for visual checks without touching personal app data."""
from pathlib import Path
import sys
import tempfile
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voiceprompt.planner import PlannerService
from voiceprompt.planner_ui import PlannerUI
from voiceprompt.sounds import SoundFeedback


def main():
    with tempfile.TemporaryDirectory(prefix="voiceprompt-preview-") as directory:
        service = PlannerService(Path(directory) / "planner.sqlite3")
        service.save_task("Learn DSA", "Practice binary search and review the time complexity.")
        service.save_task("Go for a jog")
        root = tk.Tk()
        root.withdraw()
        sounds = SoundFeedback()
        ui = PlannerUI(root, service, sounds, lambda: False)
        ui.open()
        ui.window.protocol("WM_DELETE_WINDOW", root.quit)
        service.start()
        try:
            root.mainloop()
        finally:
            ui.close()
            root.destroy()
            sounds.close()
            service.close()


if __name__ == "__main__":
    main()
