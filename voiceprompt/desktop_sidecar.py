"""Headless host for the tested dictation controller and planner services."""
from __future__ import annotations

import copy
import logging
import math
import os
import sys
import threading
import time
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


def validate_settings(settings, updates):
    if set(updates) - set(asdict(settings)):
        raise ValueError("Unsupported setting.")
    result = replace(settings, **updates)
    for name, default in asdict(settings).items():
        value = getattr(result, name)
        if isinstance(default, bool) and not isinstance(value, bool):
            raise ValueError(f"{name} must be enabled or disabled.")
        if isinstance(default, str) and (not isinstance(value, str) or len(value) > 512):
            raise ValueError(f"Invalid value for {name}.")
    for name, choices in {"backend": {"whisper", "moonshine", "parakeet", "nemotron"},
                          "cleanup_provider": {"none", "gemini", "openrouter"},
                          "hotkey": {"right_ctrl", "left_ctrl", "right_alt", "left_alt", "f8", "f9"},
                          "capture_mode": {"auto", "wasapi", "mme"}, "recording_mode": {"ptt", "toggle"},
                          "nemotron_device": {"cpu", "vulkan"}, "streaming_model": {"tiny", "small"},
                          "device": {"cpu", "cuda", "auto"}, "compute_type": {"int8", "float16", "float32", "int8_float16", "auto"}}.items():
        if getattr(result, name) not in choices:
            raise ValueError(f"Choose a supported {name.replace('_', ' ')}.")
    for name, low, high in (("cpu_threads", 1, 12), ("beam_size", 1, 10), ("max_history", 0, 500)):
        value = getattr(result, name)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{name.replace('_', ' ')} must be {low}–{high}.")
    timeout = result.cleanup_timeout_seconds
    if not isinstance(timeout, (float, int)) or isinstance(timeout, bool) or not math.isfinite(timeout) or not 1 <= timeout <= 15:
        raise ValueError("Cleanup timeout must be 1–15 seconds.")
    if not isinstance(result.replacements, dict) or len(result.replacements) > 500:
        raise ValueError("Use at most 500 dictionary entries.")
    if any(not isinstance(k, str) or not isinstance(v, str) or not k.strip() or not v.strip() or max(len(k), len(v)) > 240 for k, v in result.replacements.items()):
        raise ValueError("Dictionary entries need a source and replacement of at most 240 characters.")
    return result


class DesktopService:
    def __init__(self, controller, writer):
        self.app, self.writer = controller, writer
        self.stop = threading.Event()
        self.app.pill.on_navigation = lambda page: writer.event("navigate", {"page": page})

    def runtime(self):
        app = self.app
        with app._control:
            return {"status": app.get_status(), "ready": app._ready, "working": app._working,
                    "sessionId": app._current_id, "elapsedSeconds": app.elapsed_seconds,
                    "backlogSeconds": app.backlog_seconds, "latestText": app.latest_text,
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
        data["notifications"] = notices
        data["pendingCount"] = len(pending)
        data["now"] = now
        data["nextAlarm"] = min((a for a in data["alarms"] if a["enabled"] and a["due"] > now), key=lambda a: a["due"], default=None)
        data["counts"] = {kind: len(data[kind]) for kind in ("tasks", "alarms", "contests")}
        for kind in ("tasks", "alarms", "contests"):
            if kind != "tasks":
                data[kind].sort(key=lambda item: item.get("due", item.get("start", 0)))
            data[kind] = data[kind][:50]
        return data

    def dispatch(self, method, params):
        app = self.app
        if method == "bootstrap":
            from voiceprompt.config import gemini_api_key, openrouter_api_key
            return {"version": PROTOCOL_VERSION, "settings": asdict(app.settings), "runtime": self.runtime(),
                    "planner": self.planner_snapshot(), "history": [asdict(item) for item in app.history.load()[:20]],
                    "credentials": {"gemini": bool(gemini_api_key()), "openrouter": bool(openrouter_api_key())}}
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
            settings = validate_settings(app.settings, params.get("settings", {}))
            if os.environ.get("VOICEPROMPT_ACCEPTANCE_DIR") and settings.startup_on_boot:
                raise ValueError("Windows startup cannot be changed from an isolated verification profile.")
            app.update_settings(settings)
            return {"queued": True}
        elif method == "history.list":
            query = str(params.get("query", "")).casefold()
            offset, limit = max(0, int(params.get("offset", 0))), min(50, max(1, int(params.get("limit", 20))))
            with app._control:
                items = [asdict(item) for item in app.history.load() if query in item.text.casefold()]
            return {"items": items[offset:offset + limit], "total": len(items)}
        elif method in {"history.clear", "history.delete"}:
            with app._control:
                app.history.clear() if method.endswith("clear") else app.history.delete(str(params["id"]))
        elif method == "clipboard.copy":
            import pyperclip
            text = params.get("text", app.latest_text)
            if not isinstance(text, str) or len(text) > 100000:
                raise ValueError("Invalid clipboard text.")
            with app._control:
                app.injector.cancel_restore()
                pyperclip.copy(text)
        elif method == "credential.save":
            if os.environ.get("VOICEPROMPT_ACCEPTANCE_DIR"): raise ValueError("Provider credentials cannot be changed from an isolated verification profile.")
            from voiceprompt.credentials import save_key
            value = str(params.get("key", "")).strip()
            if not value or len(value) > 4096: raise ValueError("Enter a valid provider key.")
            save_key(str(params.get("provider")), value)
        elif method == "credential.remove":
            if os.environ.get("VOICEPROMPT_ACCEPTANCE_DIR"): raise ValueError("Provider credentials cannot be changed from an isolated verification profile.")
            from voiceprompt.credentials import remove_key
            remove_key(str(params.get("provider")))
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
            return {"items": items[offset:offset + 50], "total": len(items)}
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
        planner_at = 0.0
        try:
            while not self.stop.wait(1 / 30) and not self.app._quitting:
                state = self.runtime()
                if state != last_state:
                    self.writer.event("runtime", state)
                    last_state = state
                if state["recording"]:
                    self.writer.event("meter", {"sessionId": state["sessionId"], "values": self.app.recorder.envelope()})
                now = time.monotonic()
                if now - planner_at >= 0.5:
                    planner_at = now
                    settings = asdict(self.app.settings)
                    if settings != last_settings:
                        self.writer.event("settings", settings)
                        last_settings = settings
                    snapshot = self.planner_snapshot()
                    if snapshot != last_planner:
                        self.writer.event("planner", snapshot)
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
    with SingleInstance() as instance:
        if instance.already_running:
            writer.event("fatal", {"message": "VoicePrompt is already running. Quit the other instance first."})
            return 1
        app = VoicePromptApp(preload_model=False, presentation=(HeadlessPresentation, HeadlessPresentation))
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
