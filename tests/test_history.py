import tempfile
import unittest
from pathlib import Path

from voiceprompt.history import TranscriptionHistory


class HistoryTests(unittest.TestCase):
    def test_limit_zero_disables_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            history = TranscriptionHistory(path, limit=0)
            history.add("secret")
            self.assertFalse(path.exists())

    def test_clear_removes_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            history = TranscriptionHistory(path, limit=5)
            history.add("hello")
            self.assertEqual(history.last(), "hello")
            history.clear()
            self.assertEqual(history.last(), "")


if __name__ == "__main__":
    unittest.main()
