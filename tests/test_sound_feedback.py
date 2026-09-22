from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from voiceprompt.sound_feedback import ACTIVE_PATTERN, INACTIVE_PATTERN, SoundFeedback


class SoundFeedbackTests(unittest.TestCase):
    def test_active_cue_uses_ascending_pattern(self) -> None:
        fake_winsound = Mock()
        with patch("voiceprompt.sound_feedback.winsound", fake_winsound):
            feedback = SoundFeedback(enabled=True)
            feedback.play_active()

        self.assertEqual(
            [call.args for call in fake_winsound.Beep.call_args_list],
            list(ACTIVE_PATTERN),
        )
        self.assertLess(ACTIVE_PATTERN[0][0], ACTIVE_PATTERN[-1][0])

    def test_inactive_cue_uses_descending_pattern(self) -> None:
        fake_winsound = Mock()
        with patch("voiceprompt.sound_feedback.winsound", fake_winsound):
            feedback = SoundFeedback(enabled=True)
            feedback.play_inactive(asynchronous=False)

        self.assertEqual(
            [call.args for call in fake_winsound.Beep.call_args_list],
            list(INACTIVE_PATTERN),
        )
        self.assertGreater(INACTIVE_PATTERN[0][0], INACTIVE_PATTERN[-1][0])

    def test_disabled_feedback_is_silent(self) -> None:
        fake_winsound = Mock()
        with patch("voiceprompt.sound_feedback.winsound", fake_winsound):
            feedback = SoundFeedback(enabled=False)
            feedback.play_active()
            feedback.play_inactive(asynchronous=False)

        fake_winsound.Beep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
