from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from voiceprompt.cleanup import CloudCleanup


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps({"choices": [{"message": {"content": self.content}}]}).encode("utf-8")


class CloudCleanupTests(unittest.TestCase):
    @patch("voiceprompt.cleanup.openrouter_api_key", return_value="test-key")
    @patch("voiceprompt.cleanup.request.urlopen")
    def test_openrouter_success_reports_applied(self, urlopen, _api_key) -> None:
        urlopen.return_value = FakeResponse("This is cleaned text.")
        cleanup = CloudCleanup("openrouter", "openrouter/free", "gemini", timeout_seconds=3.5)
        result = cleanup.clean("this is cleaned text")
        self.assertEqual(result.text, "This is cleaned text.")
        self.assertTrue(result.applied)
        self.assertTrue(result.attempted)
        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(payload["model"], "openrouter/free")
        self.assertEqual(payload["provider"], {"sort": "latency"})

    @patch("voiceprompt.cleanup.openrouter_api_key", return_value="test-key")
    @patch("voiceprompt.cleanup.request.urlopen", side_effect=TimeoutError)
    def test_failure_returns_local_text_with_error(self, _urlopen, _api_key) -> None:
        result = CloudCleanup("openrouter", "openrouter/free", "gemini").clean("keep local text")
        self.assertEqual(result.text, "keep local text")
        self.assertFalse(result.applied)
        self.assertTrue(result.error)

    @patch("voiceprompt.cleanup.openrouter_api_key", return_value="test-key")
    @patch("voiceprompt.cleanup.request.urlopen")
    def test_protected_number_change_is_rejected(self, urlopen, _api_key) -> None:
        urlopen.return_value = FakeResponse("Set GPIO4 to 9000 Hz")
        result = CloudCleanup("openrouter", "openrouter/free", "gemini").clean("Set GPIO4 to 8000 Hz")
        self.assertEqual(result.text, "Set GPIO4 to 8000 Hz")
        self.assertFalse(result.applied)


if __name__ == "__main__":
    unittest.main()
