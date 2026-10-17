"""Dispatch workers before importing the desktop, input hooks, or audio drivers."""
import sys


def main():
    if len(sys.argv) in (3, 4) and sys.argv[1] == "--smoke-test":
        try:
            from voiceprompt.smoke import run
            run(sys.argv[2], hold_for_uninstall=len(sys.argv) == 4 and sys.argv[3] == "--hold-for-uninstall")
        except Exception:
            import json
            import traceback
            from pathlib import Path
            Path(sys.argv[2]).write_text(json.dumps({"error": traceback.format_exc()}, indent=2), encoding="utf-8")
            raise SystemExit(1)
    elif len(sys.argv) == 3 and sys.argv[1] == "--speech-worker":
        from voiceprompt.backend_process import run_worker
        run_worker(int(sys.argv[2]))
    elif len(sys.argv) == 4 and sys.argv[1] == "--nemotron-worker":
        from voiceprompt.nemotron_process import run_worker
        run_worker(int(sys.argv[2]), sys.argv[3])
    else:
        from voiceprompt.main import main as desktop_main
        try:
            desktop_main()
        except Exception as exc:
            from PySide6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication([])
            QMessageBox.critical(None, "VoicePrompt could not start", str(exc))
            raise SystemExit(1)


if __name__ == "__main__":
    main()
