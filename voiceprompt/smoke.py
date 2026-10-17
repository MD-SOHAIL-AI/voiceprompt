"""A frozen-build check that does not access personal data, hooks, or microphones."""
import json
import sys
from pathlib import Path


def run(output):
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
    return checks
