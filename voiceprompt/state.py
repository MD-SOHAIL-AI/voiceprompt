"""UI-independent recording states and reasons, shared with diagnostics."""
from enum import Enum


class SessionState(str, Enum):
    IDLE = "idle"
    PREPARING = "loading model"
    READY = "ready"
    STARTING = "starting"
    LISTENING = "recording"
    CATCHING_UP = "catching up"
    FINISHING = "transcribing"
    CLEANING = "cleaning"
    ERROR = "error"


class StopReason(str, Enum):
    RELEASED = "released"
    DURATION_LIMIT = "duration_limit"
    CANCELLED = "cancelled"
    CAPTURE_FAILED = "capture_failed"
    RECOGNITION_FAILED = "recognition_failed"
    TIMEOUT = "timeout"


MAX_RECORDING_SECONDS = 300.0
FINALIZATION_TIMEOUT_SECONDS = 30.0
