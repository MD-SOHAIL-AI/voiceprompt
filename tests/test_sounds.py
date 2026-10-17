from __future__ import annotations

import unittest
import wave
from array import array
from pathlib import Path
from unittest.mock import MagicMock, patch

from voiceprompt.sounds import SoundFeedback


class SoundTests(unittest.TestCase):
    @patch("voiceprompt.sounds.winsound")
    def test_async_files_no_default_sound_and_shutdown(self, win):
        win.SND_FILENAME, win.SND_ASYNC, win.SND_NODEFAULT = 0x20000, 1, 2
        sound = SoundFeedback()
        self.assertTrue(sound.play("start"))
        self.assertEqual(win.PlaySound.call_args.args[1], 0x20003)
        self.assertTrue(Path(win.PlaySound.call_args.args[0]).is_file())
        sound.close()
        self.assertFalse(sound.play("stop"))
        win.PlaySound.assert_called_with(None, 0)

    @patch("voiceprompt.sounds.winsound")
    def test_playback_errors_are_optional(self, win):
        win.PlaySound.side_effect = RuntimeError("Device missing")
        self.assertFalse(SoundFeedback().play("start"))

    def test_bundled_wavs_are_short_quiet_and_fade_to_silence(self):
        directory = Path(__file__).resolve().parents[1] / "voiceprompt" / "assets"
        for name in ("start", "stop", "reminder"):
            with wave.open(str(directory / f"{name}.wav"), "rb") as wav:
                self.assertEqual((wav.getnchannels(), wav.getsampwidth()), (1, 2))
                self.assertLessEqual(wav.getnframes() / wav.getframerate(), 0.51)
                samples = array("h", wav.readframes(wav.getnframes()))
                self.assertLess(max(abs(v) for v in samples), 2800)
                self.assertEqual(samples[0], 0)
                self.assertLess(abs(samples[-1]), 10)
