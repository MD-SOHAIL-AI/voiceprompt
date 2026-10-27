from __future__ import annotations

import logging
import math
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from voiceprompt.contests import PLATFORMS, ClistCredentials, ClistProvider, CodeforcesProvider, ContestFetchError
from voiceprompt.planner_store import PlannerStore


DEFAULT_PREFERENCES = {
    "id": "preferences", "timezone": "Asia/Kolkata", "reminder_sound": True,
    "platforms": list(PLATFORMS), "contest_minutes": 15, "summary_hour": 9,
    "daily_summary": True, "clist_username": "",
}


def local_timestamp(text: str, zone: str) -> float:
    """Validate a local minute, including nonexistent daylight saving times."""
    try:
        naive = datetime.strptime(text.strip().replace("T", " ", 1), "%Y-%m-%d %H:%M")
        aware = naive.replace(tzinfo=ZoneInfo(zone))
        if datetime.fromtimestamp(aware.timestamp(), aware.tzinfo).replace(tzinfo=None) != naive:
            raise ValueError()
        return aware.timestamp()
    except (ValueError, KeyError):
        raise ValueError("Enter a valid local date and time as YYYY-MM-DD HH:MM.") from None


def next_alarm(after: float, hour: int, minute: int, weekdays: list[int], zone: str) -> float:
    local = datetime.fromtimestamp(after, ZoneInfo(zone))
    for day in range(9):
        date = local.date() + timedelta(days=day)
        if date.weekday() not in weekdays:
            continue
        try:
            candidate = local_timestamp(f"{date} {hour:02}:{minute:02}", zone)
        except ValueError:  # Skip a nonexistent local time; repeated times fire once.
            continue
        if candidate > after:
            return candidate
    raise ValueError("Select at least one weekday for a repeating alarm.")


class PlannerService:
    """Independent scheduler. Its lock covers short DB work, never a network request."""

    def __init__(self, path: Path, *, now=time.time, monotonic=time.monotonic, credentials=None, network_enabled=True):
        self.store = PlannerStore(path)
        self._lock = self.store.lock
        self.now, self.monotonic = now, monotonic
        self.credentials = credentials or ClistCredentials()
        self.network_enabled = network_enabled
        self._stop = threading.Event()
        self._thread = None
        self._network = ThreadPoolExecutor(max_workers=1, thread_name_prefix="contest-sync")
        self._syncing = False
        self._retest_clist = False
        self._closed = False
        self._next_refresh = {"codeforces": 0.0, "clist": 0.0}
        self._failures = {"codeforces": 0, "clist": 0}
        self._last_attempt = {"codeforces": float("-inf"), "clist": float("-inf")}
        self._deadline = None
        self._recovered_timer = True
        with self.store.transaction():
            if self.store.get("preferences", "preferences") is None:
                self.store.put("preferences", dict(DEFAULT_PREFERENCES))
            if self.store.get("delivery", "version") is None:
                # Existing reminders stay actionable; upgrading must not sound
                # every old reminder as if it had just arrived.
                for item in self.store.all("notification"):
                    item.update(sound_count=3, presented_revision=item.get("revision", 0))
                    self.store.put("notification", item)
                self.store.put("delivery", {"id": "version", "version": 1})
        timer = self.store.get("timer", "active")
        if timer and timer["status"] == "running":
            self._deadline = self.monotonic() + timer["ends_at"] - self.now()

    def preferences(self) -> dict:
        return {**DEFAULT_PREFERENCES, **(self.store.get("preferences", "preferences") or {})}

    def update_preferences(self, **updates) -> None:
        with self.store.transaction():
            prefs = self.preferences()
            prefs.update({k: v for k, v in updates.items() if k in DEFAULT_PREFERENCES and k != "id"})
            ZoneInfo(prefs["timezone"])
            if not 0 <= int(prefs["summary_hour"]) <= 23 or not 0 <= int(prefs["contest_minutes"]) <= 10080:
                raise ValueError("Use a summary hour from 0–23 and a reminder lead from 0–10080 minutes.")
            prefs["summary_hour"], prefs["contest_minutes"] = int(prefs["summary_hour"]), int(prefs["contest_minutes"])
            prefs["platforms"] = [p for p in prefs["platforms"] if p in PLATFORMS]
            self.store.put("preferences", prefs)
            for contest in self.store.all("contest"):
                if contest["platform"] not in prefs["platforms"]:
                    self._dismiss_related("contest", contest["id"])

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="planner-scheduler", daemon=True)
            self._thread.start()

    def request_stop(self) -> None:
        self._stop.set()

    def close(self) -> None:
        if self._closed:
            return
        self.request_stop()
        if self._thread:
            self._thread.join()
        self._network.shutdown(wait=True, cancel_futures=True)
        self.store.close()
        self._closed = True

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
                self.refresh_contests()
            except Exception:
                logging.getLogger(__name__).exception("Planner scheduler failed")
            self._stop.wait(0.5)

    def snapshot(self) -> dict:
        with self._lock:
            timer = self.store.get("timer", "active")
            if timer and timer["status"] == "running" and self._deadline is not None:
                timer["remaining"] = max(0, self._deadline - self.monotonic())
            return {"tasks": self.store.all("task"), "timer": timer,
                    "alarms": self.store.all("alarm"), "contests": self.store.all("contest"),
                    "notifications": self.store.all("notification"), "sources": self.store.all("source"),
                    "preferences": self.preferences(), "syncing": self._syncing}

    @staticmethod
    def _title(title: str) -> str:
        if not title.strip():
            raise ValueError("Enter a name.")
        return title.strip()[:240]

    def save_task(self, title: str, notes: str = "", due: float | None = None, item_id: str | None = None) -> str:
        with self.store.transaction():
            old = self.store.get("task", item_id or "") or {}
            task = {"id": item_id or uuid.uuid4().hex, "title": self._title(title), "notes": notes[:10000],
                    "due": due, "done": old.get("done", False)}
            self.store.put("task", task)
            if old.get("due") != due:
                self._dismiss_related("task", task["id"])
            return task["id"]

    def complete_task(self, item_id: str) -> None:
        with self.store.transaction():
            task = self.store.get("task", item_id)
            if task:
                task["done"] = not task["done"]
                self.store.put("task", task)
                if task["done"]:
                    self._dismiss_related("task", item_id)

    def delete(self, kind: str, item_id: str) -> None:
        if kind not in {"task", "alarm"}:
            raise ValueError("Unsupported item type.")
        with self.store.transaction():
            self.store.delete(kind, item_id)
            self._dismiss_related(kind, item_id)

    def _dismiss_related(self, kind: str, item_id: str) -> None:
        for item in self.store.all("notification"):
            if item.get("owner") == f"{kind}:{item_id}":
                item["dismissed"] = True
                self.store.put("notification", item)

    def start_timer(self, title: str, seconds: float, *, mode="countdown", short_break=300,
                    long_break=900, rounds=4, task_id=None, replace=False) -> None:
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("Enter a duration greater than zero.")
        if mode not in {"countdown", "pomodoro"} or not 1 <= int(rounds) <= 100:
            raise ValueError("Choose a valid timer mode and 1–100 work rounds.")
        if not all(math.isfinite(v) and v > 0 for v in (short_break, long_break)):
            raise ValueError("Breaks must be longer than zero.")
        with self.store.transaction():
            old = self.store.get("timer", "active")
            if old and old["status"] in {"running", "paused"} and not replace:
                raise ValueError("A timer is already active. Confirm replacement first.")
            if old:
                self._dismiss_related("timer", old["session"])
            timer = {"id": "active", "session": uuid.uuid4().hex, "title": self._title(title), "task_id": task_id,
                     "mode": mode, "phase": "work", "phase_index": 0, "completed": 0, "rounds": int(rounds),
                     "work": seconds, "short_break": short_break, "long_break": long_break,
                     "status": "running", "remaining": seconds, "ends_at": self.now() + seconds}
            self.store.put("timer", timer)
            self._deadline = self.monotonic() + seconds
            self._recovered_timer = False

    def timer_action(self, action: str, *, expected_session: str | None = None) -> None:
        with self.store.transaction():
            timer = self.store.get("timer", "active")
            if not timer:
                return
            if expected_session is not None and timer["session"] != expected_session:
                raise ValueError("This timer changed. Refresh before trying again.")
            if action not in {"pause", "resume", "restart", "cancel"}:
                raise ValueError("Unsupported timer action.")
            if action == "pause" and timer["status"] == "running":
                timer["remaining"] = max(0, self._deadline - self.monotonic())
                timer["status"] = "paused"
            elif action == "resume" and timer["status"] == "paused":
                timer["status"] = "running"
                self._deadline = self.monotonic() + timer["remaining"]
                timer["ends_at"] = self.now() + timer["remaining"]
                self._recovered_timer = False
            elif action == "restart":
                self._dismiss_related("timer", timer["session"])
                timer.update(session=uuid.uuid4().hex, status="running", phase="work", completed=0,
                             phase_index=0, remaining=timer["work"], ends_at=self.now() + timer["work"])
                self._deadline = self.monotonic() + timer["work"]
                self._recovered_timer = False
            elif action == "cancel":
                timer["status"] = "cancelled"
                self._dismiss_related("timer", timer["session"])
            self.store.put("timer", timer)

    def save_alarm(self, title: str, due: float, weekdays: list[int] | None = None, item_id=None, *, enabled: bool | None = None) -> str:
        if not math.isfinite(due) or due <= self.now():
            raise ValueError("Choose an alarm time in the future.")
        weekdays = sorted(set(weekdays or []))
        if any(day not in range(7) for day in weekdays):
            raise ValueError("Choose valid weekdays.")
        zone = self.preferences()["timezone"]
        local = datetime.fromtimestamp(due, ZoneInfo(zone))
        if weekdays:
            due = next_alarm(due - 1, local.hour, local.minute, weekdays, zone)
        alarm = {"id": item_id or uuid.uuid4().hex, "title": self._title(title), "due": due,
                 "weekdays": weekdays, "hour": local.hour, "minute": local.minute, "timezone": zone, "enabled": True}
        with self.store.transaction():
            old = self.store.get("alarm", alarm["id"])
            alarm["enabled"] = enabled if isinstance(enabled, bool) else (old["enabled"] if old else True)
            self._dismiss_related("alarm", alarm["id"])
            self.store.put("alarm", alarm)
        return alarm["id"]

    def toggle_alarm(self, item_id: str) -> None:
        with self.store.transaction():
            alarm = self.store.get("alarm", item_id)
            if not alarm:
                return
            if not alarm["enabled"] and alarm["due"] <= self.now():
                if not alarm["weekdays"]:
                    raise ValueError("Edit this alarm to choose a future date before enabling it.")
                alarm["due"] = next_alarm(self.now(), alarm["hour"], alarm["minute"], alarm["weekdays"], alarm["timezone"])
            alarm["enabled"] = not alarm["enabled"]
            if not alarm["enabled"]:
                self._dismiss_related("alarm", item_id)
            self.store.put("alarm", alarm)

    def acknowledge(self, item_id: str, snooze: bool = False, *, expected_revision: int | None = None) -> None:
        with self.store.transaction():
            item = self.store.get("notification", item_id)
            if item:
                if expected_revision is not None and item.get("revision", 0) != expected_revision:
                    raise ValueError("This reminder changed. Refresh before trying again.")
                if item.get("dismissed"):
                    return
                item["dismissed"] = not snooze
                item["due"] = min(self.now() + 300, item.get("expires") or float("inf")) if snooze else item["due"]
                item["revision"] = item.get("revision", 0) + 1
                item["sound_count"] = 0
                item["last_sound"] = 0
                item["presented_revision"] = -1
                self.store.put("notification", item)

    def mark_presented(self, item_id: str, revision: int) -> None:
        with self.store.transaction():
            item = self.store.get("notification", item_id)
            if item and item.get("revision", 0) == revision:
                item["presented_revision"] = revision
                self.store.put("notification", item)

    def claim_reminder_sound(self) -> bool:
        """Persist bounded delivery attempts so restarts do not replay alerts."""
        now = self.now()
        with self.store.transaction():
            delivery = self.store.get("delivery", "sound") or {"id": "sound", "last": 0}
            if now - delivery["last"] < 10:
                return False
            due = []
            for item in self.store.all("notification"):
                maximum = 3 if item.get("owner", "").startswith(("alarm:", "timer:")) else 1
                if not item["dismissed"] and item["due"] <= now and (not item.get("expires") or item["expires"] > now) and item.get("sound_count", 0) < maximum:
                    due.append(item)
            if not due:
                return False
            for item in due:
                item["sound_count"] = item.get("sound_count", 0) + 1
                item["last_sound"] = now
                self.store.put("notification", item)
            self.store.put("delivery", {"id": "sound", "last": now})
            return bool(self.preferences()["reminder_sound"])

    def _notify(self, item_id: str, title: str, detail: str, *, owner="", url="", expires=None) -> None:
        if self.store.get("notification", item_id) is None:
            self.store.put("notification", {"id": item_id, "title": title, "detail": detail, "owner": owner,
                                           "url": url, "due": self.now(), "created": self.now(), "expires": expires,
                                           "dismissed": False, "revision": 0})

    def tick(self) -> None:
        now = self.now()
        with self.store.transaction():
            self._tick_timer(now)
            for task in self.store.all("task"):
                if not task["done"] and task["due"] is not None and task["due"] <= now:
                    self._notify(f"task:{task['id']}:{task['due']}", task["title"], "Task reminder", owner=f"task:{task['id']}")
            for alarm in self.store.all("alarm"):
                if alarm["enabled"] and alarm["due"] <= now:
                    self._notify(f"alarm:{alarm['id']}:{alarm['due']}", alarm["title"], "Scheduled alarm", owner=f"alarm:{alarm['id']}")
                    if alarm["weekdays"]:
                        alarm["due"] = next_alarm(now, alarm["hour"], alarm["minute"], alarm["weekdays"], alarm["timezone"])
                    else:
                        alarm["enabled"] = False
                    self.store.put("alarm", alarm)
            self._tick_contests(now)
            for item in self.store.all("notification"):
                # Due tasks need their acknowledgment tombstone until the task is removed.
                if (item["dismissed"] and not item["owner"].startswith("task:") and item["created"] < now - 30 * 86400) or (item.get("expires") and item["expires"] <= now):
                    self.store.delete("notification", item["id"])
            for contest in self.store.all("contest"):
                if contest["end"] < now - 30 * 86400:
                    self.store.delete("contest", contest["id"])

    def _tick_timer(self, now: float) -> None:
        timer = self.store.get("timer", "active")
        if not timer or timer["status"] != "running" or self._deadline is None:
            return
        remaining = self._deadline - self.monotonic()
        if remaining > 0:
            self._recovered_timer = False
            # Keep restart recovery correct if the system clock was adjusted.
            if abs(timer["ends_at"] - now - remaining) > 2:
                timer["ends_at"] = now + remaining
                self.store.put("timer", timer)
            return
        overdue = self._recovered_timer or remaining < -5
        self._recovered_timer = False
        phase = timer["phase"]
        detail = "Session finished" if timer["mode"] == "countdown" else f"{phase.replace('_', ' ').capitalize()} finished"
        self._notify(f"timer:{timer['session']}:{timer['phase_index']}", timer["title"], detail, owner=f"timer:{timer['session']}")
        timer["remaining"] = 0
        timer["status"] = "completed"
        if timer["mode"] == "pomodoro":
            if phase == "work":
                timer["completed"] += 1
                timer["phase"] = "long_break" if timer["completed"] >= timer["rounds"] else "short_break"
            elif phase == "long_break":
                timer["phase"] = "finished"
            else:
                timer["phase"] = "work"
            if timer["phase"] != "finished":
                seconds = timer[timer["phase"]]
                timer.update(remaining=seconds, ends_at=now + seconds, status="paused" if overdue else "running")
                timer["phase_index"] += 1
                self._deadline = self.monotonic() + seconds
        self.store.put("timer", timer)

    def _tick_contests(self, now: float) -> None:
        prefs = self.preferences()
        contests = [c for c in self.store.all("contest") if c["platform"] in prefs["platforms"] and not c.get("muted") and c["end"] > now]
        for contest in contests:
            legacy_id = f"contest:{contest['id']}:{contest['start']}"
            if contest["start"] <= now:
                # Replace the advance reminder when the start stage becomes due.
                # A restart after the start produces just the current stage.
                advance = self.store.get("notification", legacy_id)
                if advance and not advance["dismissed"]:
                    advance["dismissed"] = True
                    self.store.put("notification", advance)
                self._notify(legacy_id + ":started", contest["name"], f"{PLATFORMS[contest['platform']]} · Contest has started",
                             owner=f"contest:{contest['id']}", url=contest["url"], expires=contest["end"])
            elif contest["start"] - prefs["contest_minutes"] * 60 <= now:
                self._notify(legacy_id, contest["name"], f"{PLATFORMS[contest['platform']]} · Starts soon",
                             owner=f"contest:{contest['id']}", url=contest["url"], expires=contest["end"])
        local = datetime.fromtimestamp(now, ZoneInfo(prefs["timezone"]))
        if prefs["daily_summary"] and local.hour >= prefs["summary_hour"]:
            today = [c for c in contests if c["start"] > now and datetime.fromtimestamp(c["start"], local.tzinfo).date() == local.date()]
            if today:
                detail = "\n".join(f"{datetime.fromtimestamp(c['start'], local.tzinfo):%H:%M} — {c['name']}" for c in sorted(today, key=lambda c: c["start"]))
                midnight = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), local.tzinfo).timestamp()
                self._notify(f"summary:{local.date()}:{prefs['timezone']}", "Today's contests", detail, expires=midnight)

    def mute_contest(self, item_id: str) -> None:
        with self.store.transaction():
            contest = self.store.get("contest", item_id)
            if contest:
                contest["muted"] = not contest.get("muted", False)
                self.store.put("contest", contest)
                if contest["muted"]:
                    self._dismiss_related("contest", item_id)

    def refresh_contests(self, force=False) -> bool:
        with self._lock:
            if not self.network_enabled or self._stop.is_set() or self._syncing:
                return False
            sources = [s for s in self._next_refresh if self.monotonic() >= self._next_refresh[s]]
            # Manual refresh observes a minimum interval too, protecting provider quotas.
            if force:
                sources = [s for s in self._next_refresh if self.monotonic() - self._last_attempt[s] >= 60]
            if not sources:
                return False
            self._syncing = True
            self._network.submit(self._sync, sources)
            return True

    def connect_clist(self, username: str, key: str) -> None:
        self.credentials.save(username, key)
        self.update_preferences(clist_username=username.strip())
        with self._lock:
            self._next_refresh["clist"] = max(self.monotonic(), self._last_attempt["clist"] + 6.1)
            self._retest_clist = self._syncing
        self.refresh_contests()

    def _wait_network(self, seconds: float) -> None:
        if self._stop.wait(seconds):
            raise ContestFetchError("Contest refresh stopped.")

    def _sync(self, sources: list[str]) -> None:
        try:
            for source in sources:
                if self._stop.is_set():
                    break
                try:
                    with self._lock:
                        self._last_attempt[source] = self.monotonic()
                    prefs = self.preferences()
                    if source == "codeforces":
                        provider = CodeforcesProvider()
                    else:
                        username = prefs["clist_username"]
                        provider = ClistProvider(username, self.credentials.get(username), self._wait_network)
                    contests = provider.fetch(self.now())
                    if self._stop.is_set():
                        break
                    with self.store.transaction():
                        self._merge_contests(source, contests)
                        self._failures[source] = 0
                        self.store.put("source", {"id": source, "updated": self.now(), "error": ""})
                    delay = 1800
                except Exception as exc:
                    # Never log request headers, provider payloads, or credentials.
                    message = str(exc) if isinstance(exc, ContestFetchError) else "Contest refresh failed. Cached schedules remain available."
                    self._failures[source] += 1
                    delay = max(getattr(exc, "retry_after", 60), min(1800, 60 * 2 ** min(self._failures[source] - 1, 5)))
                    with self.store.transaction():
                        previous = self.store.get("source", source) or {"id": source, "updated": None}
                        self.store.put("source", {**previous, "error": message})
                with self._lock:
                    self._next_refresh[source] = self.monotonic() + delay
        finally:
            with self._lock:
                self._syncing = False
                if self._retest_clist:
                    self._next_refresh["clist"] = max(self.monotonic(), self._last_attempt["clist"] + 6.1)
                    self._retest_clist = False

    def _merge_contests(self, source: str, incoming: list[dict]) -> None:
        by_id = {c["id"]: c for c in incoming}
        for old in self.store.all("contest"):
            if old["source"] != source:
                continue
            new = by_id.get(old["id"])
            if new is None or new["start"] != old["start"] or new["end"] != old["end"]:
                self._dismiss_related("contest", old["id"])
            if new is None:
                self.store.delete("contest", old["id"])
        for contest in by_id.values():
            old = self.store.get("contest", contest["id"]) or {}
            self.store.put("contest", {**contest, "muted": old.get("muted", False)})
