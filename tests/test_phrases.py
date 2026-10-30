import unittest
import numpy as np
from voiceprompt.phrases import PhraseBuffer


class PhraseTests(unittest.TestCase):
    def test_variable_blocks_and_hard_splits_preserve_every_sample_once(self):
        buffer = PhraseBuffer(lambda _: [], sample_rate=100, max_seconds=10)
        audio = np.arange(2753, dtype=np.float32)
        output = []
        for offset in range(0, len(audio), 37):
            output.extend(buffer.push(audio[offset:offset+37]))
        output.extend(buffer.push(np.empty(0), final=True))
        np.testing.assert_array_equal(np.concatenate(output), audio)
        self.assertLessEqual(max(map(len, output)), 1000)
        self.assertEqual(buffer.push(np.empty(0), final=True), [])

    def test_completed_phrase_keeps_trailing_samples_for_next_phrase(self):
        buffer = PhraseBuffer(lambda audio: [{"end": 60}], sample_rate=100)
        audio = np.arange(150, dtype=np.float32)
        output = buffer.push(audio)
        output.extend(buffer.push(np.empty(0), final=True))
        self.assertEqual([len(chunk) for chunk in output], [60,90])
        np.testing.assert_array_equal(np.concatenate(output), audio)
