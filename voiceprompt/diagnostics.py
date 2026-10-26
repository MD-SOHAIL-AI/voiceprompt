from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timezone


class Diagnostics:
    """Bounded JSONL performance logs, without audio or dictated text."""

    def __init__(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self._logger = logging.Logger(f"VoicePrompt.metrics.{id(self)}", level=logging.INFO)
        handler = RotatingFileHandler(directory / "performance.jsonl", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(handler)

    def record(self, event: str, **metrics: object) -> None:
        self._logger.info(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **metrics}, ensure_ascii=True))

    def close(self) -> None:
        for handler in self._logger.handlers:
            handler.close()
