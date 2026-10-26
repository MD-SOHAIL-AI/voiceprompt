"""A frozen-build check that does not access personal data, hooks, or microphones."""
import json
import sys
import os
import time
from pathlib import Path


def run(output, hold_for_uninstall=False, *, headless=False):
    from voiceprompt import __version__
    from voiceprompt.backend_process import ManagedTranscriber
    from voiceprompt.config import Settings
    from voiceprompt.audio import RNNoise
    if not headless:
        from PySide6 import __version__ as qt_version
        from PySide6.QtWidgets import QApplication, QWidget
        app = QApplication.instance() or QApplication([])
        widget = QWidget()
        widget.resize(100, 100)
    checks = {"version": __version__, "qt": None if headless else qt_version, "tauri": bool(headless and os.environ.get("VOICEPROMPT_DESKTOP_PID")), "frozen": bool(getattr(sys, "frozen", False)), "workers": {}}
    for name in ("whisper", "moonshine", "parakeet", "nemotron"):
        backend = ManagedTranscriber(Settings(backend=name))
        try:
            backend._start()
            checks["workers"][name] = backend._exchange("describe", timeout=60)
        finally:
            backend.close()
    # The release includes the optional native noise library, without its plotting stack.
    try:
        RNNoise().close()
        checks["rnnoise"] = True
    except RuntimeError:
        checks["rnnoise"] = False
    Path(output).write_text(json.dumps(checks, indent=2), encoding="utf-8")
    if not headless:
        widget.close()
    if hold_for_uninstall:
        # Exercise uninstall with a real frozen process, loaded native libraries
        # and a live speech child, without touching a microphone or personal data.
        from voiceprompt.instance import ShutdownRequest
        with ShutdownRequest() as shutdown:
            backend = ManagedTranscriber(Settings(backend="whisper"))
            try:
                backend._start()
                backend._exchange("describe", timeout=60)
                checks["holding_for_uninstall"] = True
                Path(output).write_text(json.dumps(checks, indent=2), encoding="utf-8")
                if headless:
                    while not shutdown.requested():
                        time.sleep(0.1)
                else:
                    from PySide6.QtCore import QTimer
                    timer = QTimer()
                    timer.timeout.connect(lambda: app.quit() if shutdown.requested() else None)
                    timer.start(100)
                    app.exec()
                checks["shutdown_received"] = shutdown.requested()
            finally:
                backend.close()
            Path(output).write_text(json.dumps(checks, indent=2), encoding="utf-8")
    return checks
