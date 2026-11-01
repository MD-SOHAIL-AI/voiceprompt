import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from voiceprompt.config import Settings
from voiceprompt.history import TranscriptionHistory
from voiceprompt.planner import PlannerService


def make_controller(directory, *, onboarding=False):
    directory = Path(directory)
    controller = SimpleNamespace(
        settings=Settings(onboarding_completed=not onboarding), status="ready", detail="Hold Right Ctrl to dictate into another application.",
        latest_text="", last_error="", elapsed_seconds=0.0, backlog_seconds=0.0,
        download_progress={}, _failed_audio=None, _ready=True, _working=False,
        _session=None, _quitting=False, _updating=False, _planner_error="", _pending_settings=None,
        recorder=SimpleNamespace(level=0.0, is_recording=False),
        history=TranscriptionHistory(directory / "history.json"),
        planner=PlannerService(directory / "planner.sqlite3"), injector=Mock(),
    )
    controller.get_status = lambda: controller.status
    controller._reminder_audio_busy = lambda: controller._working
    for name in ("preload_model", "check_microphone", "stop_recording", "cancel_current", "quit", "retry_failed", "discard_failed", "update_pill_position", "_play_reminder_sound", "_planner_root_ready"):
        setattr(controller, name, Mock())
    controller.update_settings = lambda settings: setattr(controller, "settings", settings)
    return controller
