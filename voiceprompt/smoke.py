"""A frozen-build check that does not access personal data, hooks, or microphones."""
import json
import sys
from pathlib import Path


def run(output, hold_for_uninstall=False):
    from PySide6 import __version__ as qt_version
    from PySide6.QtWidgets import QApplication, QWidget
    from voiceprompt import __version__
    from voiceprompt.backend_process import ManagedTranscriber
    from voiceprompt.config import Settings
    from voiceprompt.audio import RNNoise
    app = QApplication.instance() or QApplication([])
    widget = QWidget()
    widget.resize(100, 100)
    checks = {"version": __version__, "qt": qt_version, "frozen": bool(getattr(sys, "frozen", False)), "workers": {}}
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
    widget.close()
    if hold_for_uninstall:
        # Exercise uninstall with a real frozen process, loaded native libraries
        # and a live speech child, without touching a microphone or personal data.
        from PySide6.QtCore import QTimer
        from voiceprompt.instance import ShutdownRequest
        with ShutdownRequest() as shutdown:
            backend = ManagedTranscriber(Settings(backend="whisper"))
            try:
                backend._start()
                backend._exchange("describe", timeout=60)
                checks["holding_for_uninstall"] = True
                Path(output).write_text(json.dumps(checks, indent=2), encoding="utf-8")
                timer = QTimer()
                timer.timeout.connect(lambda: app.quit() if shutdown.requested() else None)
                timer.start(100)
                app.exec()
                checks["shutdown_received"] = shutdown.requested()
            finally:
                backend.close()
            Path(output).write_text(json.dumps(checks, indent=2), encoding="utf-8")
    return checks
