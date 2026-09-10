from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


import uuid

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
        if not text:
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
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def last(self) -> str:
        items = self.load()
        return items[0].text if items else ""

    def load(self) -> list[HistoryItem]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        
        loaded_items = []
        for item in data:
            if not isinstance(item, dict) or not str(item.get("text", "")).strip():
                continue
            loaded_items.append(
                HistoryItem(
                    text=str(item.get("text", "")),
                    created_at=str(item.get("created_at", "")),
                    duration_seconds=float(item.get("duration_seconds", 0.0)),
                    source=str(item.get("source", "local")),
                    id=str(item.get("id", uuid.uuid4().hex)),
                )
            )
        return loaded_items
