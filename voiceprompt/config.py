from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

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
    config_version: int = 7
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
    startup_on_boot: bool = False
    vad_filter: bool = True
    whisper_phrase_decoding: bool = False
    max_history: int = 50
    recording_mode: str = "ptt"
    sound_feedback: bool = True
    pill_position_x: int = -1
    pill_position_y: int = -1
    replacements: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_REPLACEMENTS))


def config_dir() -> Path:
    acceptance = os.environ.get("VOICEPROMPT_ACCEPTANCE_DIR")
    if acceptance:
        path = Path(acceptance)
        if not path.is_absolute():
            raise ValueError("The isolated acceptance directory must be absolute.")
        path.mkdir(parents=True, exist_ok=True)
        return path
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


def load_settings(path: Path | None = None, *, migration_backup=True) -> Settings:
    path = path or config_path()
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
    if type(version) is not int or not 0 <= version <= 7:
        raise ValueError("These settings need a newer version of VoicePrompt. Your data has been kept.")
    if version < 7 and migration_backup:
        backup = path.with_suffix(f".v{version}.bak")
        if not backup.exists():
            shutil.copy2(path, backup)

    allowed = Settings.__dataclass_fields__.keys()
    values: dict[str, Any] = {key: value for key, value in data.items() if key in allowed}
    defaults = asdict(Settings())
    for key in list(values):
        if isinstance(defaults[key], bool) and type(values[key]) is not bool:
            values[key] = defaults[key]
        elif isinstance(defaults[key], str) and not isinstance(values[key], str):
            values[key] = defaults[key]
    settings = Settings(**values)
    settings.onboarding_completed = data.get("onboarding_completed", True) is True
    if not isinstance(settings.sound_feedback, bool):
        settings.sound_feedback = True
    settings.config_version = 7
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
    return validate_settings(settings, {})


def recover_settings(*, use_backup=True):
    """Explicit recovery keeps the damaged file and never reads provider keys."""
    import uuid
    path = config_path()
    settings = None
    if use_backup:
        for backup in sorted(path.parent.glob("config.v*.bak"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                settings = load_settings(backup, migration_backup=False)
                break
            except (ValueError, OSError, TypeError):
                continue
        if settings is None:
            raise ValueError("No compatible settings backup was found. You can start with defaults; the original file will be kept.")
    else:
        settings = Settings()
    if path.exists():
        shutil.copy2(path, path.with_name("config.unreadable." + uuid.uuid4().hex + ".json"))
    save_settings(settings)


def save_settings(settings: Settings) -> None:
    validate_settings(settings, {})
    path = config_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(settings), indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def validate_settings(settings: Settings, updates: dict) -> Settings:
    if not isinstance(updates, dict) or set(updates) - set(asdict(Settings())):
        raise ValueError("Unsupported setting.")
    result = replace(settings, **updates)
    for name, default in asdict(Settings()).items():
        value = getattr(result, name)
        if isinstance(default, bool) and type(value) is not bool:
            raise ValueError(f"{name} must be enabled or disabled.")
        if isinstance(default, str) and (not isinstance(value, str) or len(value) > 512):
            raise ValueError(f"Invalid value for {name}.")
    choices = {
        "backend": {"whisper", "moonshine", "parakeet", "nemotron"},
        "hotkey": {"right_ctrl", "left_ctrl", "right_alt", "left_alt", "f8", "f9"},
        "capture_mode": {"auto", "wasapi", "mme"}, "recording_mode": {"ptt", "toggle"},
        "nemotron_device": {"cpu", "vulkan"}, "streaming_model": {"tiny", "small"},
        "device": {"cpu", "cuda", "auto"}, "compute_type": {"int8", "float16", "float32", "int8_float16", "auto"},
    }
    for name, allowed in choices.items():
        if getattr(result, name) not in allowed:
            raise ValueError(f"Choose a supported {name.replace('_', ' ')}.")
    for name, low, high in (("config_version", 7, 7), ("cpu_threads", 1, 12), ("beam_size", 1, 10),
                             ("max_history", 0, 500), ("pill_position_x", -100000, 100000), ("pill_position_y", -100000, 100000)):
        value = getattr(result, name)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{name.replace('_', ' ')} must be {low}–{high}.")
    if not isinstance(result.replacements, dict) or len(result.replacements) > 500:
        raise ValueError("Use at most 500 dictionary entries.")
    if any(not isinstance(k, str) or not isinstance(v, str) or not k.strip() or not v.strip() or max(len(k), len(v)) > 240 for k, v in result.replacements.items()):
        raise ValueError("Dictionary entries need a source and replacement of at most 240 characters.")
    if len(json.dumps(asdict(result), ensure_ascii=False).encode("utf-8")) > 128000:
        raise ValueError("Settings exceed the safe storage size. Shorten the custom dictionary.")
    return result
