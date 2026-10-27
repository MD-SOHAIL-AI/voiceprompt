"""Bounded, versioned stdio transport. stdout is exclusively protocol data."""
from __future__ import annotations

import json
import threading

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 1024 * 1024


def read_messages(stream):
    while True:
        raw = stream.readline(MAX_MESSAGE_BYTES + 1)
        if not raw:
            return
        if len(raw) > MAX_MESSAGE_BYTES:
            # Drain the oversized frame without allocating its remainder.
            while raw and not raw.endswith(b"\n"):
                raw = stream.readline(MAX_MESSAGE_BYTES + 1)
            yield None, "Command exceeds the maximum message size."
            continue
        try:
            value = json.loads(raw)
            if not isinstance(value, dict) or not isinstance(value.get("id"), int) or isinstance(value["id"], bool):
                raise ValueError("A command requires an integer request id.")
            if type(value.get("version")) is not int or value["version"] != PROTOCOL_VERSION or not isinstance(value.get("method"), str):
                raise ValueError("Unsupported protocol version or command.")
            if not isinstance(value.get("params", {}), dict):
                raise ValueError("Command parameters must be an object.")
            yield value, None
        except (ValueError, UnicodeError) as exc:
            yield None, str(exc)


class Writer:
    def __init__(self, stream):
        self.stream, self.lock, self.sequence = stream, threading.Lock(), 0

    def send(self, value):
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > MAX_MESSAGE_BYTES:
            raise ValueError("Result exceeds the message limit. Request a smaller page.")
        with self.lock:
            self.stream.write(encoded)
            self.stream.flush()

    def event(self, name, payload):
        # Sequence assignment and writing share one lock to preserve ordering.
        with self.lock:
            self.sequence += 1
            value = {"version": PROTOCOL_VERSION, "event": name, "sequence": self.sequence, "payload": payload}
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8") + b"\n"
            if len(encoded) > MAX_MESSAGE_BYTES:
                raise ValueError("Event exceeds the message limit.")
            self.stream.write(encoded)
            self.stream.flush()
