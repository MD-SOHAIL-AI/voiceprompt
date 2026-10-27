"""Launch the TypeScript desktop; retain an explicit legacy Qt entry for recovery."""
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
        if '--legacy-qt' not in sys.argv:
            return launch_desktop()
        sys.argv.remove('--legacy-qt')
        from voiceprompt.main import main as desktop_main
        try:
            desktop_main()
        except Exception as exc:
            from PySide6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication([])
            QMessageBox.critical(None, "VoicePrompt could not start", str(exc))
            raise SystemExit(1)


def launch_desktop():
    import os
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    candidates = [root / 'dist/VoicePrompt/VoicePrompt.exe']
    local = os.environ.get('LOCALAPPDATA')
    if local:
        candidates.append(Path(local) / 'Programs/VoicePrompt/VoicePrompt.exe')
    for executable in candidates:
        if executable.is_file():
            subprocess.Popen([str(executable)], cwd=str(executable.parent), creationflags=0x08000000 if os.name == 'nt' else 0)
            return 0
    message = ('Build the TypeScript desktop with scripts/build_desktop.ps1, or run '
               'npm run tauri -- dev from desktop/. Use --legacy-qt only for the previous interface.')
    if os.name == 'nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, 'VoicePrompt desktop is not built', 0x40)
    else:
        print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
