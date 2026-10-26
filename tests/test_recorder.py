from __future__ import annotations

import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from voiceprompt.recorder import PushToTalkRecorder, RecorderConfig


class RecorderTests(unittest.TestCase):
    def ready_recorder(self):
        recorder = PushToTalkRecorder()
        recorder._stream = MagicMock(latency=0.01)
        recorder.start()
        recorder._started_at = time.perf_counter() - 1
        return recorder

    def feed(self, recorder, value=1.0, overflow=False):
        recorder._on_audio(np.full((160, 1), value, dtype=np.float32), 160, None, SimpleNamespace(input_overflow=overflow))

    def test_grace_period_retains_final_phoneme_and_reuses_stream(self):
        recorder = self.ready_recorder()
        stream = recorder._stream
        self.feed(recorder)
        with patch("voiceprompt.recorder.time.sleep", side_effect=lambda _: self.feed(recorder, 2)):
            result = recorder.stop()
        np.testing.assert_array_equal(result.audio[-160:], np.full(160, 2))
        self.assertEqual(len(result.audio), 320)
        stream.close.assert_not_called()
        recorder.start()
        self.assertIs(recorder._stream, stream)
        recorder.close()
        stream.close.assert_called_once()

    def test_short_tap_is_ignored_despite_grace_period(self):
        recorder = self.ready_recorder()
        recorder._started_at = time.perf_counter()
        self.feed(recorder)
        with patch("voiceprompt.recorder.time.sleep"):
            self.assertIsNone(recorder.stop())

    def test_idle_stream_does_not_retain_or_deliver_audio(self):
        recorder = PushToTalkRecorder()
        recorder.on_audio_chunk = MagicMock()
        self.feed(recorder)
        self.assertEqual(recorder._frames, [])
        recorder.on_audio_chunk.assert_not_called()

    def test_dropped_frames_and_delivery_failure_are_observable(self):
        recorder = self.ready_recorder()
        recorder.on_audio_chunk = MagicMock(side_effect=RuntimeError("delivery failed"))
        self.feed(recorder, overflow=True)
        self.assertEqual(recorder.input_overflows, 1)
        self.assertIn("delivery failed", recorder.callback_error)

    def test_start_failure_cleans_up_stream(self):
        recorder = PushToTalkRecorder()
        stream = MagicMock()
        stream.start.side_effect = RuntimeError("disconnected")
        recorder._stream = stream
        with self.assertRaisesRegex(RuntimeError, "disconnected"):
            recorder.start()
        self.assertFalse(recorder.is_recording)
        self.assertIsNone(recorder._stream)
        stream.close.assert_called_once()

    @patch("voiceprompt.recorder.sd")
    def test_prefers_wasapi_and_uses_native_rate_when_needed(self, sd):
        sd.default.device = (0, 0)
        sd.query_devices.return_value = [
            {"name": "Mic", "max_input_channels": 1, "hostapi": 0, "default_samplerate": 48000},
            {"name": "Mic", "max_input_channels": 1, "hostapi": 1, "default_samplerate": 48000},
        ]
        sd.query_hostapis.return_value = [{"name": "MME"}, {"name": "Windows WASAPI"}]
        sd.check_input_settings.side_effect = [ValueError("unsupported rate"), None]
        sd.InputStream.return_value.latency = 0.01
        recorder = PushToTalkRecorder()
        recorder.prepare()
        self.assertEqual(recorder.sample_rate, 48000)
        self.assertEqual(recorder.host_api, "Windows WASAPI")
        self.assertIn("unsupported rate", recorder.fallback_reason)
        self.assertEqual(sd.InputStream.call_args.kwargs["blocksize"], 0)
        self.assertEqual(sd.InputStream.call_args.kwargs["latency"], "low")

    @patch("voiceprompt.recorder.sd")
    def test_missing_selected_microphone_does_not_select_unrelated_input(self, sd):
        sd.query_devices.return_value = []
        sd.query_hostapis.return_value = []
        recorder = PushToTalkRecorder(RecorderConfig(microphone="Missing"))
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            recorder.prepare()

    @patch("voiceprompt.recorder.sd")
    def test_truncated_mme_name_matches_full_wasapi_device(self, sd):
        sd.default.device = (0, 0)
        sd.query_devices.return_value = [
            {"name": "Microphone Array (Realtek(R) Au", "max_input_channels": 1, "hostapi": 0, "default_samplerate": 48000},
            {"name": "Microphone Array (Realtek(R) Audio)", "max_input_channels": 1, "hostapi": 1, "default_samplerate": 48000},
        ]
        sd.query_hostapis.return_value = [{"name": "MME"}, {"name": "Windows WASAPI"}]
        sd.InputStream.return_value.latency = 0.022
        recorder = PushToTalkRecorder()
        recorder.prepare()
        self.assertEqual(recorder.host_api, "Windows WASAPI")
        self.assertEqual(sd.InputStream.call_args.kwargs["device"], 1)

    @patch("voiceprompt.recorder.sd")
    def test_openable_but_unstartable_wasapi_falls_back_before_ready(self, sd):
        sd.default.device = (0, 0)
        sd.query_devices.return_value = [
            {"name": "Mic", "max_input_channels": 1, "hostapi": 0, "default_samplerate": 16000},
            {"name": "Mic", "max_input_channels": 1, "hostapi": 1, "default_samplerate": 16000},
        ]
        sd.query_hostapis.return_value = [{"name": "Windows WASAPI"}, {"name": "MME"}]
        broken = MagicMock()
        broken.start.side_effect = RuntimeError("driver cannot start")
        working = MagicMock(latency=0.1)
        sd.InputStream.side_effect = [broken, working]
        recorder = PushToTalkRecorder()
        recorder.on_audio_chunk = MagicMock()
        recorder.prepare()
        self.assertEqual(recorder.host_api, "MME")
        self.assertIn("driver cannot start", recorder.fallback_reason)
        broken.close.assert_called_once()
        working.start.assert_called_once()
        working.stop.assert_called_once()
        recorder.on_audio_chunk.assert_not_called()
        self.assertFalse(recorder.is_recording)
