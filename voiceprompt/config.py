from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from platformdirs import user_config_dir


APP_NAME = "Voice Prompt"


DEFAULT_REPLACEMENTS = {
    "chat g p t": "ChatGPT",
    "g mini": "Gemini",
    "brahmsulge": "Brahmshosh",
    "brahm shosh": "Brahmshosh",
    "brahm sosh": "Brahmshosh",
    "brahmshosh": "Brahmshosh",
}

UNSAFE_LEGACY_REPLACEMENTS = {
    "cloud": "claude",
    "god": "claude",
}

BALANCED_MODEL = "Systran/faster-distil-whisper-small.en"


@dataclass
class Settings:
    config_version: int = 2
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
    pill_position_x: int = -1
    pill_position_y: int = -1
    replacements: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_REPLACEMENTS))


def config_dir() -> Path:
    path = Path(user_config_dir(APP_NAME, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
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
    except (OSError, json.JSONDecodeError):
        return Settings()

    allowed = Settings.__dataclass_fields__.keys()
    values: dict[str, Any] = {key: value for key, value in data.items() if key in allowed}
    if "cleanup_provider" not in data and data.get("gemini_cleanup"):
        values["cleanup_provider"] = "gemini"
    settings = Settings(**values)
    settings.config_version = 2
    if settings.cleanup_provider not in {"none", "openrouter", "gemini"}:
        settings.cleanup_provider = "none"
    settings.cleanup_timeout_seconds = max(1.0, min(15.0, float(settings.cleanup_timeout_seconds)))
    settings.gemini_cleanup = settings.cleanup_provider == "gemini"
    if settings.gemini_model in {"gemini-2.0-flash", "gemini-2.0-flash-001"}:
        settings.gemini_model = "gemini-2.5-flash-lite"
    normalized_replacements = {
        str(source).strip(): str(target).strip()
        for source, target in settings.replacements.items()
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
    path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


def gemini_api_key() -> str:
    load_dotenv()
    return os.getenv("GEMINI_API_KEY", "").strip()


def openrouter_api_key() -> str:
    load_dotenv()
    return os.getenv("OPENROUTER_API_KEY", "").strip()
