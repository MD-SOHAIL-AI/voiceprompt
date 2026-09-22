from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class HistoryItem:
    text: str
    created_at: str
    duration_seconds: float = 0.0
    source: str = "local"
    id: str = ""


class TranscriptionHistory:
    def __init__(self, path: Path, limit: int = 50) -> None:
        self.path = path
        self.limit = limit
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def add(self, text: str, duration_seconds: float = 0.0, source: str = "local") -> None:
        text = text.strip()
        if not text or self.limit <= 0:
            return
        with self._lock:
            items = self.load()
            items.insert(
                0,
                HistoryItem(
                    text=text,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    duration_seconds=duration_seconds,
                    source=source,
                    id=uuid.uuid4().hex,
                ),
            )
            self._write(items[: self.limit])

    def last(self) -> str:
        items = self.load()
        return items[0].text if items else ""

    def clear(self) -> None:
        with self._lock:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass

    def load(self) -> list[HistoryItem]:
        with self._lock:
            if not self.path.exists():
                return []
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return []

            loaded_items: list[HistoryItem] = []
            for item in data if isinstance(data, list) else []:
                if not isinstance(item, dict) or not str(item.get("text", "")).strip():
                    continue
                try:
                    duration = float(item.get("duration_seconds", 0.0))
                except (TypeError, ValueError):
                    duration = 0.0
                loaded_items.append(
                    HistoryItem(
                        text=str(item.get("text", "")),
                        created_at=str(item.get("created_at", "")),
                        duration_seconds=duration,
                        source=str(item.get("source", "local")),
                        id=str(item.get("id") or uuid.uuid4().hex),
                    )
                )
            return loaded_items

    def _write(self, items: list[HistoryItem]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(item) for item in items], indent=2), encoding="utf-8")
        tmp.replace(self.path)
