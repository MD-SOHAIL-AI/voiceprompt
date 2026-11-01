from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


import uuid
import hashlib
import math

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

    def add(self, text: str, duration_seconds: float = 0.0, source: str = "local") -> None:
        text = text.strip()
        if not text or self.limit <= 0:
            return
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
        data = [asdict(item) for item in items[: self.limit]]
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def clear(self):
        try:
            self.load()
        except (OSError, ValueError):
            import shutil
            shutil.copy2(self.path, self.path.with_name("history.unreadable." + uuid.uuid4().hex + ".json"))
        self._write([])

    def _write(self, items):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps([asdict(item) for item in items], ensure_ascii=False, allow_nan=False), encoding="utf-8")
        temporary.replace(self.path)

    def delete(self, item_id: str):
        self._write([item for item in self.load() if item.id != item_id])

    def last(self) -> str:
        items = self.load()
        return items[0].text if items else ""

    def load(self) -> list[HistoryItem]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("History could not be read. The original file has been kept; Clear history can start a fresh list.") from exc
        
        if not isinstance(data, list):
            raise ValueError("History has an unsupported format. The original file has been kept.")
        loaded_items = []
        for index, item in enumerate(data):
            if not isinstance(item, dict) or not str(item.get("text", "")).strip():
                continue
            try:
                duration = max(0.0, float(item.get("duration_seconds", 0.0)))
            except (TypeError, ValueError):
                duration = 0.0
            if not math.isfinite(duration):
                duration = 0.0
            loaded_items.append(
                HistoryItem(
                    text=str(item.get("text", "")),
                    created_at=str(item.get("created_at", "")),
                    duration_seconds=duration,
                    source=str(item.get("source", "local")),
                    id=str(item.get("id") or hashlib.sha256(f"{index}:{item.get('created_at', '')}:{item.get('text', '')}".encode()).hexdigest()[:32]),
                )
            )
        return loaded_items
