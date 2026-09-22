import unittest
from unittest.mock import patch

from voiceprompt.injector import TextInjector


class InjectorTests(unittest.TestCase):
    @patch("voiceprompt.injector.pyperclip.copy")
    @patch("voiceprompt.injector.pyperclip.paste", return_value="new user value")
    def test_restore_does_not_overwrite_new_clipboard(self, paste, copy) -> None:
        injector = TextInjector()
        with patch("voiceprompt.injector.time.sleep"):
            injector._restore_later("old", "dictation")
        copy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
