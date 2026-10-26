from __future__ import annotations

import unittest
import importlib.util
from unittest.mock import patch

import numpy as np

from voiceprompt.audio import AudioProcessor, RNNoise


class AudioTests(unittest.TestCase):
    def test_variable_chunks_match_whole_recording_resample(self):
        audio = np.sin(np.arange(44100, dtype=np.float32) * 0.05)
        whole = AudioProcessor(44100)
        expected = whole.process(audio, final=True)
        processor = AudioProcessor(44100)
        actual = np.concatenate([processor.process(audio[i:i+731]) for i in range(0, len(audio), 731)] + [processor.process(np.empty(0, dtype=np.float32), final=True)])
        self.assertEqual(len(actual), 16000)
        np.testing.assert_allclose(actual, expected, atol=1e-6)

    def test_native_16k_is_not_resampled(self):
        processor = AudioProcessor(16000)
        audio = np.ones(100, dtype=np.float32)
        np.testing.assert_array_equal(processor.process(audio), audio)
        self.assertEqual(len(processor.process(np.empty(0), final=True)), 0)

    def test_missing_noise_dependency_has_actionable_error(self):
        with patch("voiceprompt.audio.importlib.util.find_spec", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "requirements-noise"):
                RNNoise()

    @unittest.skipUnless(importlib.util.find_spec("pyrnnoise"), "Optional RNNoise is not installed")
    def test_native_noise_pipeline_flushes_tail_without_changing_duration(self):
        audio = np.random.default_rng(7).normal(0, 0.02, 48000 + 333).astype(np.float32)
        processor = AudioProcessor(48000, True)
        try:
            chunks = [processor.process(audio[i:i+777]) for i in range(0, len(audio), 777)]
            chunks.append(processor.process(np.empty(0, dtype=np.float32), final=True))
            output = np.concatenate(chunks)
            self.assertEqual(len(output), round(len(audio) / 3))
            self.assertTrue(np.isfinite(output).all())
            self.assertLess(float(np.max(np.abs(output))), 1.0)
        finally:
            processor.close()
