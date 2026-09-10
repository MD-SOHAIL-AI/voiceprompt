from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from voiceprompt.config import load_settings


class ConfigMigrationTests(unittest.TestCase):
    def test_migrates_model_and_removes_unsafe_replacements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "model": "base.en",
                        "replacements": {
                            "cloud": "claude",
                            "God": "claude",
                            "my project": "MyProject",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch("voiceprompt.config.config_path", return_value=path):
                settings = load_settings()

        self.assertEqual(settings.model, "base.en")
        self.assertNotIn("cloud", settings.replacements)
        self.assertNotIn("God", settings.replacements)
        self.assertEqual(settings.replacements["my project"], "MyProject")
        self.assertEqual(settings.replacements["brahmsulge"], "Brahmshosh")


if __name__ == "__main__":
    unittest.main()
