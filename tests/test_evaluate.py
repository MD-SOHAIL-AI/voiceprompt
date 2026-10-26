from __future__ import annotations

import unittest
from copy import deepcopy
from unittest.mock import patch

from voiceprompt.evaluate import select_candidate, summarize, word_errors


class EvaluationTests(unittest.TestCase):
    def test_word_error_rate_counts_substitutions_deletions_insertions(self):
        self.assertEqual(word_errors("one two three", "one four"), (2, 3))
        self.assertEqual(word_errors("Hello, world!", "hello world"), (0, 2))
        self.assertEqual(word_errors("", "hallucination"), (1, 0))

    def test_small_smoke_set_cannot_promote_a_model(self):
        result = {"candidate": "baseline", "noise_suppression": False, "summary": {"clean": {"clips": 1}}, "rows": []}
        selection = select_candidate([result])
        self.assertEqual(selection["selected"], "baseline")
        self.assertIn("30 speech clips", selection["reason"])

    def test_silence_does_not_lower_speech_latency(self):
        rows = [
            {"condition": "clean", "errors": 0, "reference_words": 2, "hypothesis": "hello world", "duration_seconds": 10, "release_to_final_seconds": 3},
            {"condition": "noise", "errors": 0, "reference_words": 0, "hypothesis": "", "duration_seconds": 2, "release_to_final_seconds": 0.1},
        ]
        with patch("voiceprompt.evaluate.process_peak_mb", return_value=200):
            result = summarize(rows)
        self.assertAlmostEqual(result["estimated_median_release_to_paste_seconds"], 3.14)

    def test_full_set_requires_accuracy_and_sustained_processing_gates(self):
        def report(name, latency, noisy_errors):
            rows = []
            for condition in ("clean", "fan", "traffic"):
                for _ in range(10):
                    rows.append({
                        "condition": condition, "errors": 0 if condition == "clean" else noisy_errors,
                        "reference_words": 10, "hypothesis": "speech", "duration_seconds": 5,
                        "release_to_final_seconds": latency, "decoding_seconds": 1,
                    })
            rows.extend([
                {"condition": "noise", "errors": 0, "reference_words": 0, "hypothesis": "", "duration_seconds": 5, "release_to_final_seconds": 0.1},
                {"condition": "stress", "errors": 0, "reference_words": 100, "hypothesis": "speech", "duration_seconds": 60, "release_to_final_seconds": latency, "decoding_seconds": 30},
            ])
            with patch("voiceprompt.evaluate.process_peak_mb", return_value=200):
                summary = summarize(rows)
            return {"candidate": name, "noise_suppression": False, "cpu_threads": 4, "rows": rows, "summary": summary}

        baseline = report("baseline", 3, 2)
        candidate = report("moonshine-tiny", 1, 1)
        self.assertEqual(select_candidate([baseline, candidate])["selected"], "moonshine-tiny")
        for field, value in (("max_processing_rtf", 1.1), ("peak_process_mb", 1200)):
            failing = deepcopy(candidate)
            failing["summary"][field] = value
            self.assertEqual(select_candidate([baseline, failing])["selected"], "baseline")
        failing = deepcopy(candidate)
        failing["summary"]["clean"]["wer"] = 0.02
        self.assertEqual(select_candidate([baseline, failing])["selected"], "baseline")
        failing = deepcopy(candidate)
        failing["summary"]["noise"]["hallucinated_clips"] = 1
        self.assertEqual(select_candidate([baseline, failing])["selected"], "baseline")
