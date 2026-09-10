from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from voiceprompt.cleanup import CloudCleanup


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps({"choices": [{"message": {"content": self.content}}]}).encode("utf-8")


class CloudCleanupTests(unittest.TestCase):
    @patch("voiceprompt.cleanup.openrouter_api_key", return_value="test-key")
    @patch("voiceprompt.cleanup.request.urlopen")
    def test_openrouter_uses_free_router_and_latency_sort(self, urlopen, _api_key) -> None:
        urlopen.return_value = FakeResponse("This is cleaned text.")
        cleanup = CloudCleanup("openrouter", "openrouter/free", "gemini", timeout_seconds=3.5)

        result = cleanup.clean("this is cleaned text")

        self.assertEqual(result, "This is cleaned text.")
        api_request = urlopen.call_args.args[0]
        payload = json.loads(api_request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "openrouter/free")
        self.assertEqual(payload["provider"], {"sort": "latency"})
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 3.5)

    @patch("voiceprompt.cleanup.openrouter_api_key", return_value="test-key")
    @patch("voiceprompt.cleanup.request.urlopen", side_effect=TimeoutError)
    def test_openrouter_failure_returns_local_text(self, _urlopen, _api_key) -> None:
        cleanup = CloudCleanup("openrouter", "openrouter/free", "gemini")
        self.assertEqual(cleanup.clean("keep local text"), "keep local text")

    @patch("voiceprompt.cleanup.openrouter_api_key", return_value="test-key")
    @patch("voiceprompt.cleanup.request.urlopen")
    def test_implausibly_long_cleanup_is_rejected(self, urlopen, _api_key) -> None:
        urlopen.return_value = FakeResponse("extra " * 100)
        cleanup = CloudCleanup("openrouter", "openrouter/free", "gemini")
        self.assertEqual(cleanup.clean("short dictation"), "short dictation")


if __name__ == "__main__":
    unittest.main()
