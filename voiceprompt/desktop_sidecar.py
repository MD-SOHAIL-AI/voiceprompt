"""Headless host for the tested dictation controller and planner services."""
from __future__ import annotations

import copy
import logging
import math
import os
import sys
import threading
import time
import json
from dataclasses import asdict, replace
from pathlib import Path

from voiceprompt.desktop_protocol import PROTOCOL_VERSION, Writer, read_messages


class HeadlessPresentation:
    def __init__(self, controller=None, **callbacks):
        self.controller = controller
        self.on_navigation = lambda page: None

    def set_status(self, status): pass
    def refresh(self): pass
    def stop(self): pass
    def call(self, callback): callback()
    def show_page(self, name): self.on_navigation(name)


from voiceprompt.config import validate_settings


def ordered_items(kind, items):
    if kind in {"notification", "history"}:
        return items
    field = {"alarm": "due", "contest": "start"}.get(kind)
    return sorted(items, key=lambda item: ((item.get(field) or 0) if field else 0, item["id"]))


def wire_page(kind, items, offset=0, limit=50):
    """Keep snapshots small; full task notes are fetched only when editing."""
    result, size = [], 0
    for item in ordered_items(kind, items)[offset:offset + limit]:
        row = dict(item)
        truncated = False
        for key, value in row.items():
            if isinstance(value, str) and key not in {"id", "url", "owner"}:
                row[key] = value[:240 if key == "notes" else 1024]
                if key == "text" and row[key] != value: truncated = True
        if truncated: row["truncated"] = True
        encoded = len(json.dumps(row, ensure_ascii=False).encode("utf-8"))
        if result and size + encoded > 96000:
            break
        result.append(row)
        size += encoded
    return result


class DesktopService:
    def __init__(self, controller, writer):
        self.app, self.writer = controller, writer
        self.stop = threading.Event()
        self.app.pill.on_navigation = lambda page: writer.event("navigate", {"page": page})

    def emit(self, name, payload):
        try:
            self.writer.event(name, payload)
        except ValueError:
            self.writer.event("protocol-error", {"message": "A desktop update exceeded its size limit. Open a smaller page; voice typing is still available."})

    def runtime(self):
        app = self.app
        with app._control:
            return {"status": app.get_status(), "ready": app._ready, "working": app._working,
                    "sessionId": app._current_id, "elapsedSeconds": app.elapsed_seconds,
                    "operationSeconds": max(0, time.perf_counter() - app._work_started_at) if app._working else 0,
                    "recognitionPhase": app._session.phase if app._session else "",
                    "processingSeconds": max(0, time.perf_counter() - app._session.released_at) if app._session and app._session.released_at else 0,
                    "backlogSeconds": app.backlog_seconds, "latestText": app.latest_text,
                    "storageWarning": getattr(app, "storage_warning", ""),
                    "credentialWarning": getattr(app, "credential_warning", ""),
                    "desiredSettingsRevision": getattr(app, "_settings_revision", 0),
                    "appliedSettingsRevision": getattr(app, "_applied_settings_revision", 0),
                    "error": app.last_error, "detail": app.detail, "failedAudio": bool(app._failed_audio),
                    "recording": bool(app.recorder.is_recording), "insertionStatus": getattr(app, "insertion_status", "none"),
                    "deferReminders": bool(app._reminder_audio_busy()),
                    "acceptanceProfile": bool(os.environ.get("VOICEPROMPT_ACCEPTANCE_DIR")),
                    "download": app.download_progress, "runtimeInfo": app.runtime_info(), "plannerError": app._planner_error}

    def planner_snapshot(self):
        try:
            return self._planner_snapshot()
        except Exception:
            self.app._planner_error = "Planner data could not be read. Your existing files have been kept."
            return None

    def _planner_snapshot(self):
        planner = self.app.planner
        if planner is None:
            return None
        data = planner.snapshot()
        now = planner.now()
        pending = [n for n in data["notifications"] if not n["dismissed"] and n["due"] <= now and (not n.get("expires") or n["expires"] > now)]
        rank = lambda n: (0 if n.get("owner", "").startswith(("alarm:", "timer:")) else 1 if n.get("owner", "").startswith("contest:") else 2, n["due"])
        pending.sort(key=rank)
        contests = {c["id"]: c for c in data["contests"]}
        notices = []
        for item in pending[:50]:
            item = dict(item)
            owner = item.get("owner", "")
            item["kind"] = owner.split(":", 1)[0] or "summary"
            item["contest"] = contests.get(owner.removeprefix("contest:")) if item["kind"] == "contest" else None
            notices.append(item)
        data["notifications"] = wire_page("notification", notices)
        data["pendingCount"] = len(pending)
        data["now"] = now
        data["nextAlarm"] = min((a for a in data["alarms"] if a["enabled"] and a["due"] > now), key=lambda a: a["due"], default=None)
        data["counts"] = {kind: len(data[kind]) for kind in ("tasks", "alarms", "contests")}
        for kind in ("tasks", "alarms", "contests"):
            data[kind] = wire_page(kind.removesuffix("s"), data[kind])
        return data

    def dispatch(self, method, params):
        app = self.app
        if os.environ.get("VOICEPROMPT_ACCEPTANCE_DIR") and method in {"prepare", "microphone.check", "record.start", "record.retry"}:
            raise ValueError("Microphone capture and speech preparation are disabled in an isolated verification profile.")
        if method == "bootstrap":
            sequence = self.writer.sequence
            return {"version": PROTOCOL_VERSION, "snapshotSequence": sequence, "settings": asdict(app.settings), "runtime": self.runtime(),
                    "planner": self.planner_snapshot(), "history": []}
        if method == "runtime": return self.runtime()
        if method == "prepare": app.preload_model()
        elif method == "microphone.check": app.check_microphone()
        elif method == "microphone.list":
            from voiceprompt.recorder import microphones
            return microphones()
        elif method == "record.start":
            if not app._ready:
                raise ValueError("Prepare your microphone and model before recording.")
            app.start_recording()
        elif method == "record.stop": app.stop_recording()
        elif method == "record.cancel": app.cancel_current()
        elif method == "record.retry": app.retry_failed()
        elif method == "record.discard": app.discard_failed()
        elif method == "settings.save":
            with app._control:
                settings = validate_settings(getattr(app, "_desired_settings", None) or getattr(app, "_pending_settings", None) or app.settings, params.get("settings", {}))
                if os.environ.get("VOICEPROMPT_ACCEPTANCE_DIR") and settings.startup_on_boot:
                    raise ValueError("Windows startup cannot be changed from an isolated verification profile.")
                revision = app.update_settings(settings)
            return {"queued": True, "revision": revision}
        elif method == "sound.preview":
            if app._working: raise ValueError("Finish recording before previewing a sound.")
            if params.get("cue") not in {"start", "stop"}: raise ValueError("Choose a recording sound.")
            app.sounds.play(params["cue"])
        elif method == "privacy.retire_credentials":
            from voiceprompt.credentials import retire_cloud_credentials
            app.credential_warning = retire_cloud_credentials()
            return {"ok": not bool(app.credential_warning)}
        elif method == "history.list":
            query = str(params.get("query", "")).casefold()
            offset, limit = max(0, int(params.get("offset", 0))), min(50, max(1, int(params.get("limit", 20))))
            with app._control:
                items = [asdict(item) for item in app.history.load() if query in item.text.casefold()]
            page = wire_page("history", items, offset, limit)
            return {"items": page, "total": len(items), "nextOffset": offset + len(page)}
        elif method == "history.item":
            with app._control:
                item = next((item for item in app.history.load() if item.id == params.get("id")), None)
            if item is None: raise ValueError("This transcript was removed. Refresh history.")
            return asdict(item)
        elif method in {"history.clear", "history.delete"}:
            with app._control:
                app.history.clear() if method.endswith("clear") else app.history.delete(str(params["id"]))
                app.storage_warning = ""
        elif method == "clipboard.copy":
            import pyperclip
            text = params.get("text", app.latest_text)
            if not isinstance(text, str) or len(text) > 100000:
                raise ValueError("Invalid clipboard text.")
            with app._control:
                app.injector.cancel_restore()
                pyperclip.copy(text)
        elif method == "island.position": app.update_pill_position(int(params["x"]), int(params["y"]))
        elif method == "shutdown":
            self.stop.set()
            app.quit()
        elif method.startswith("planner."):
            return self.planner_command(method[8:], params)
        else: raise ValueError("Unsupported desktop command.")
        return {"ok": True}

    def planner_command(self, method, p):
        planner = self.app.planner
        if planner is None: raise ValueError(self.app._planner_error)
        if method == "snapshot": return self.planner_snapshot()
        if method == "page":
            kind = p.get("kind")
            if kind not in {"task", "alarm", "contest"}: raise ValueError("Unsupported list.")
            items = planner.store.all(kind)
            offset = max(0, int(p.get("offset", 0)))
            page = wire_page(kind, items, offset)
            return {"items": page, "total": len(items), "nextOffset": offset + len(page)}
        if method == "item":
            if p.get("kind") != "task": raise ValueError("Unsupported item type.")
            item = planner.store.get("task", str(p["id"]))
            if item is None: raise ValueError("This task was removed. Refresh the list.")
            return item
        from voiceprompt.planner import local_timestamp
        if method == "task.save":
            due = local_timestamp(str(p["localDue"]), planner.preferences()["timezone"]) if p.get("localDue") else p.get("due")
            planner.save_task(str(p.get("title", "")), str(p.get("notes", "")), due, p.get("id"))
        elif method == "task.complete": planner.complete_task(str(p["id"]))
        elif method == "delete": planner.delete(str(p["kind"]), str(p["id"]))
        elif method == "timer.start":
            expected = p.get("expectedSession")
            with planner.store.transaction():
                current = planner.store.get("timer", "active")
                if p.get("replace") and current and current["session"] != expected:
                    raise ValueError("The active timer changed. Review it before replacing it.")
                planner.start_timer(str(p.get("title", "Focus session")), float(p["seconds"]), mode=p.get("mode", "countdown"),
                    short_break=float(p.get("shortBreak", 300)), long_break=float(p.get("longBreak", 900)),
                    rounds=int(p.get("rounds", 4)), task_id=p.get("taskId"), replace=p.get("replace") is True)
        elif method == "timer.action": planner.timer_action(str(p["action"]), expected_session=str(p["session"]))
        elif method == "alarm.save":
            due = local_timestamp(str(p["localDue"]), planner.preferences()["timezone"]) if p.get("localDue") else float(p["due"])
            planner.save_alarm(str(p.get("title", "Alarm")), due, p.get("weekdays"), p.get("id"), enabled=p.get("enabled"))
        elif method == "alarm.toggle": planner.toggle_alarm(str(p["id"]))
        elif method == "notification.act": planner.acknowledge(str(p["id"]), p.get("snooze") is True, expected_revision=int(p["revision"]))
        elif method == "notification.presented": planner.mark_presented(str(p["id"]), int(p["revision"]))
        elif method == "notifications.presented":
            items = p.get("items", [])
            if not isinstance(items, list) or len(items) > 50: raise ValueError("Invalid reminder batch.")
            for item in items: planner.mark_presented(str(item["id"]), int(item["revision"]))
        elif method == "preferences": planner.update_preferences(**p)
        elif method == "contests.refresh": return {"started": planner.refresh_contests(force=True)}
        elif method == "contests.mute": planner.mute_contest(str(p["id"]))
        elif method == "contests.connect":
            if os.environ.get("VOICEPROMPT_ACCEPTANCE_DIR"): raise ValueError("Provider credentials cannot be changed from an isolated verification profile.")
            planner.connect_clist(str(p["username"]), str(p["key"]))
        else: raise ValueError("Unsupported planner command.")
        return {"ok": True}

    def pump(self):
        last_state = last_planner = last_settings = None
        planner_at = runtime_at = 0.0
        try:
            while not self.stop.wait(1 / 30) and not self.app._quitting:
                if self.app.shutdown_requested():
                    self.app.quit()
                    self.stop.set()
                    break
                now = time.monotonic()
                if now - runtime_at >= .1:
                    runtime_at = now
                    state = self.runtime()
                    if state != last_state:
                        update = dict(state)
                        if last_state and state["latestText"] == last_state["latestText"]:
                            update.pop("latestText")
                        self.emit("runtime", update)
                        last_state = state
                if self.app.recorder.is_recording:
                    self.emit("meter", {"sessionId": self.app._current_id, "values": self.app.recorder.envelope()})
                if now - planner_at >= 0.5:
                    planner_at = now
                    settings = asdict(self.app.settings)
                    if settings != last_settings:
                        self.emit("settings", settings)
                        last_settings = settings
                    snapshot = self.planner_snapshot()
                    if snapshot != last_planner:
                        self.emit("planner", snapshot)
                        last_planner = snapshot
                    planner = self.app.planner
                    if snapshot is not None and planner and not self.app._reminder_audio_busy() and planner.claim_reminder_sound():
                        self.app._play_reminder_sound()
        except (BrokenPipeError, OSError):
            self.stop.set()
        except Exception:
            logging.exception("Desktop event delivery failed")
            self.stop.set()
        finally:
            if not self.app._quitting: self.app.quit()


def main():
    # Libraries may print model-loading notices; keep them away from the protocol.
    protocol_out = sys.stdout.buffer
    sys.stdout = sys.stderr
    from voiceprompt.main import VoicePromptApp
    from voiceprompt.instance import SingleInstance
    writer = Writer(protocol_out)
    acceptance = os.environ.get("VOICEPROMPT_ACCEPTANCE_DIR")
    if acceptance:
        import hashlib
        identity = hashlib.sha256(str(Path(acceptance).resolve()).encode()).hexdigest()[:20]
        instance_guard = SingleInstance(name="Local\\VoicePrompt.Acceptance." + identity)
    else:
        instance_guard = SingleInstance()
    with instance_guard as instance:
        if instance.already_running:
            writer.event("fatal", {"message": "Another VoicePrompt instance is running. Quit it from the system tray, then select Restart engine."})
            return 1
        from voiceprompt.config import load_settings, recover_settings
        try:
            load_settings()
        except (ValueError, OSError):
            writer.event("fatal", {"code": "settings_recovery", "message": "Settings could not be loaded. Restore a settings backup or start with defaults. Your original files will be kept."})
            for command, error in read_messages(sys.stdin.buffer):
                if error: continue
                try:
                    if command["method"] != "configuration.recover":
                        raise ValueError("Settings need recovery. Use the recovery controls before restarting the engine.")
                    mode = command.get("params", {}).get("mode")
                    if mode not in {"backup", "defaults"}: raise ValueError("Choose backup or defaults.")
                    recover_settings(use_backup=mode == "backup")
                    writer.send({"id": command["id"], "ok": True, "result": {"ok": True}})
                    return 0
                except Exception as exc:
                    message = str(exc) if isinstance(exc, ValueError) else "Settings could not be recovered. Check disk space and folder permissions."
                    writer.send({"id": command["id"], "ok": False, "error": {"message": message}})
            return 1
        app = VoicePromptApp(preload_model=False, presentation=(HeadlessPresentation, HeadlessPresentation))
        from voiceprompt.instance import ShutdownRequest
        shutdown_request = ShutdownRequest()
        app.shutdown_requested = shutdown_request.requested
        service = DesktopService(app, writer)
        if not os.environ.get("VOICEPROMPT_ACCEPTANCE_DIR"): app.hotkey.start()
        if app.planner: app.planner.start()
        worker = threading.Thread(target=service.pump, name="desktop-events", daemon=True)
        worker.start()
        writer.event("ready", {"version": PROTOCOL_VERSION})
        if app.settings.onboarding_completed and app.settings.preload_model: app.preload_model()
        try:
            for command, error in read_messages(sys.stdin.buffer):
                if error:
                    writer.event("protocol-error", {"message": error})
                    continue
                request_id = command["id"]
                try:
                    result = service.dispatch(command["method"], command.get("params", {}))
                    writer.send({"id": request_id, "ok": True, "result": result})
                except Exception as exc:
                    # Do not reflect credential parameters or provider exceptions.
                    message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "The operation could not finish. Please retry."
                    writer.send({"id": request_id, "ok": False, "error": {"code": "operation_failed", "message": message}})
                if service.stop.is_set(): break
        finally:
            service.stop.set()
            if not app._quitting: app.quit()
            worker.join(timeout=2)
            shutdown_request.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
