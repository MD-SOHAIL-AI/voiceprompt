from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from platformdirs import user_config_dir


APP_NAME = "VoicePrompt"


DEFAULT_REPLACEMENTS = {
    "chat g p t": "ChatGPT",
    "g mini": "Gemini",
}

UNSAFE_LEGACY_REPLACEMENTS = {
    "cloud": "claude",
    "god": "claude",
}

BALANCED_MODEL = "Systran/faster-distil-whisper-small.en"


@dataclass
class Settings:
    config_version: int = 6
    onboarding_completed: bool = False
    backend: str = "whisper"
    nemotron_device: str = "vulkan"
    streaming_model: str = "tiny"
    cpu_threads: int = 4
    microphone: str = ""
    capture_mode: str = "auto"
    noise_suppression: bool = False
    hotkey: str = "right_ctrl"
    model: str = "base.en"
    language: str = "en"
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 3
    preload_model: bool = True
    paste_injection: bool = True
    preserve_clipboard: bool = True
    cleanup_provider: str = "none"
    cleanup_timeout_seconds: float = 4.0
    openrouter_model: str = "openrouter/free"
    gemini_cleanup: bool = False
    gemini_model: str = "gemini-2.5-flash-lite"
    startup_on_boot: bool = False
    vad_filter: bool = True
    max_history: int = 50
    recording_mode: str = "ptt"
    sound_feedback: bool = True
    pill_position_x: int = -1
    pill_position_y: int = -1
    replacements: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_REPLACEMENTS))


def config_dir() -> Path:
    path = Path(user_config_dir(APP_NAME, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    # The early public build used a spaced application name. Copy its files,
    # retaining the originals, only when this profile has no corresponding file.
    legacy = Path(user_config_dir("Voice Prompt", appauthor=False))
    if legacy != path and legacy.is_dir():
        for name in ("config.json", "history.json"):
            source, destination = legacy / name, path / name
            if source.is_file() and not destination.exists():
                shutil.copy2(source, destination)
    return path


def config_path() -> Path:
    return config_dir() / "config.json"


def history_path() -> Path:
    return config_dir() / "history.json"


def load_settings() -> Settings:
    load_dotenv()
    path = config_path()
    if not path.exists():
        settings = Settings()
        save_settings(settings)
        return settings

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("VoicePrompt could not read its settings. Your original file has been kept; restore a backup or repair config.json.") from exc
    if not isinstance(data, dict):
        raise ValueError("VoicePrompt settings must be an object. Your original file has been kept.")
    version = data.get("config_version", 0)
    if not isinstance(version, int) or version > 6:
        raise ValueError("These settings need a newer version of VoicePrompt. Your data has been kept.")
    if version < 6:
        backup = path.with_suffix(f".v{version}.bak")
        if not backup.exists():
            shutil.copy2(path, backup)

    allowed = Settings.__dataclass_fields__.keys()
    values: dict[str, Any] = {key: value for key, value in data.items() if key in allowed}
    if "cleanup_provider" not in data and data.get("gemini_cleanup"):
        values["cleanup_provider"] = "gemini"
    settings = Settings(**values)
    settings.onboarding_completed = data.get("onboarding_completed", True) is True
    if not isinstance(settings.sound_feedback, bool):
        settings.sound_feedback = True
    settings.config_version = 6
    if settings.hotkey not in {"right_ctrl", "left_ctrl", "right_alt", "left_alt", "f8", "f9"}:
        settings.hotkey = "right_ctrl"
    if settings.recording_mode not in {"ptt", "toggle"}:
        settings.recording_mode = "ptt"
    try:
        settings.max_history = max(0, min(500, int(settings.max_history)))
    except (TypeError, ValueError):
        settings.max_history = 50
    if settings.backend not in {"whisper", "moonshine", "parakeet", "nemotron"}:
        settings.backend = "whisper"
    if settings.nemotron_device not in {"vulkan", "cpu"}:
        settings.nemotron_device = "vulkan"
    if settings.streaming_model not in {"small", "tiny"}:
        settings.streaming_model = "tiny"
    if settings.capture_mode not in {"auto", "wasapi", "mme"}:
        settings.capture_mode = "auto"
    try:
        settings.cpu_threads = max(1, min(12, int(settings.cpu_threads)))
    except (TypeError, ValueError):
        settings.cpu_threads = 4
    settings.microphone = str(settings.microphone or "")
    if settings.backend in {"moonshine", "parakeet", "nemotron"}:
        settings.language = "en"
    if settings.cleanup_provider not in {"none", "openrouter", "gemini"}:
        settings.cleanup_provider = "none"
    try:
        settings.cleanup_timeout_seconds = max(1.0, min(15.0, float(settings.cleanup_timeout_seconds)))
    except (TypeError, ValueError):
        settings.cleanup_timeout_seconds = 4.0
    settings.gemini_cleanup = settings.cleanup_provider == "gemini"
    if settings.gemini_model in {"gemini-2.0-flash", "gemini-2.0-flash-001"}:
        settings.gemini_model = "gemini-2.5-flash-lite"
    normalized_replacements = {
        str(source).strip(): str(target).strip()
        for source, target in (settings.replacements if isinstance(settings.replacements, dict) else DEFAULT_REPLACEMENTS).items()
        if str(source).strip() and str(target).strip()
    }
    normalized_replacements = {
        source: target
        for source, target in normalized_replacements.items()
        if UNSAFE_LEGACY_REPLACEMENTS.get(source.casefold()) != target.casefold()
    }
    for source, target in DEFAULT_REPLACEMENTS.items():
        normalized_replacements.setdefault(source, target)
    settings.replacements = normalized_replacements
    return settings


def save_settings(settings: Settings) -> None:
    path = config_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    temporary.replace(path)


def gemini_api_key() -> str:
    load_dotenv()
    return _provider_key("gemini", "GEMINI_API_KEY")


def openrouter_api_key() -> str:
    load_dotenv()
    return _provider_key("openrouter", "OPENROUTER_API_KEY")


def _provider_key(provider, variable):
    from voiceprompt.credentials import get_key
    return get_key(provider) or os.getenv(variable, "").strip()
