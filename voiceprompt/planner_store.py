from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing, contextmanager
from pathlib import Path


class PlannerStore:
    """Small transactional local store; no transcripts or credentials are stored here."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing_database = path.is_file() and path.stat().st_size > 0
        self.lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=3000")
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            self._db.close()
            raise RuntimeError("This Planner database needs a newer version of VoicePrompt.")
        if existing_database and not path.with_suffix(".pre-desktop.sqlite3").exists():
            with closing(sqlite3.connect(path.with_suffix(".pre-desktop.sqlite3"))) as backup:
                self._db.backup(backup)
        self._db.execute("CREATE TABLE IF NOT EXISTS items (kind TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(kind,id))")
        self._db.execute("PRAGMA user_version=1")
        self._db.commit()

    @contextmanager
    def transaction(self):
        with self.lock:
            with self._db:
                yield

    def all(self, kind: str) -> list[dict]:
        with self.lock:
            return [json.loads(row[0]) for row in self._db.execute("SELECT data FROM items WHERE kind=?", (kind,))]

    def get(self, kind: str, item_id: str) -> dict | None:
        with self.lock:
            row = self._db.execute("SELECT data FROM items WHERE kind=? AND id=?", (kind, item_id)).fetchone()
            return json.loads(row[0]) if row else None

    def put(self, kind: str, item: dict) -> None:
        # The caller groups related writes with transaction().
        with self.lock:
            self._db.execute("INSERT INTO items(kind,id,data) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data",
                             (kind, item["id"], json.dumps(item, allow_nan=False)))

    def delete(self, kind: str, item_id: str) -> None:
        with self.lock:
            self._db.execute("DELETE FROM items WHERE kind=? AND id=?", (kind, item_id))

    def close(self) -> None:
        with self.lock:
            self._db.close()
