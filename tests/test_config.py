from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from voiceprompt.config import load_settings


class ConfigMigrationTests(unittest.TestCase):
    def test_v2_english_default_migrates_to_multilingual_and_private_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "config_version": 2,
                        "model": "base.en",
                        "language": "en",
                        "replacements": {
                            "cloud": "claude",
                            "my project": "MyProject",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("voiceprompt.config.config_path", return_value=path):
                settings = load_settings()

        self.assertEqual(settings.model, "base")
        self.assertEqual(settings.language, "")
        self.assertFalse(settings.save_history)
        self.assertNotIn("cloud", settings.replacements)
        self.assertEqual(settings.replacements["my project"], "MyProject")


if __name__ == "__main__":
    unittest.main()
