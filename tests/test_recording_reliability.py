"""Regressions for long holds, decoding stalls, cancellation, and retry."""
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from voiceprompt.config import Settings
from voiceprompt.hotkeys import PushToTalkHotkey, KEYS
from voiceprompt.recorder import Recording, PushToTalkRecorder, RecorderConfig
from voiceprompt.session import AudioQueue, DictationSession, IncompleteRecording, ReplayRecorder
from voiceprompt.state import StopReason


class StreamingRecorder:
    sample_rate = 16000
    input_overflows = 0
    capture_failed = False
    callback_error = ""
    capture_open_seconds = input_latency_seconds = 0.0
    host_api = "test"
    is_recording = False

    def __init__(self, session, *, seconds=3.1, release_after=0.1):
        self.session, self.seconds, self.release_after = session, seconds, release_after
        self.stopped_at = None

    def prepare(self):
        pass

    def start(self):
        self.is_recording = True
        for _ in range(round(self.seconds * 10)):
            self.on_audio_chunk(np.ones(1600, dtype=np.float32), 16000)
        if self.release_after is not None:
            self.timer = threading.Timer(self.release_after, self.session.request_release)
            self.timer.start()

    def stop(self, **kwargs):
        self.is_recording = False
        self.stopped_at = time.perf_counter()
        return Recording(np.empty(0), 16000, self.seconds)


class ReliabilityTests(unittest.TestCase):
    def test_three_second_backlog_is_kept_and_finalized_once(self):
        session = DictationSession(1)
        backend = Mock()
        backend.finish_session.return_value = "all words"
        recorder = StreamingRecorder(session)
        consumed = []
        backend.accept_audio.side_effect = lambda audio: consumed.append(len(audio))
        text, duration = session.run(recorder, backend, hotwords="", noise_suppression=False)
        self.assertEqual(text, "all words")
        self.assertEqual(duration, 3.1)
        self.assertEqual(sum(consumed), 49600)
        self.assertGreater(session.audio_queue.peak_seconds, 2)
        backend.finish_session.assert_called_once()

    def test_microphone_stops_on_release_while_decoder_is_blocked(self):
        session = DictationSession(1)
        recorder = StreamingRecorder(session, release_after=0.03)
        backend = Mock()
        backend.finish_session.return_value = "text"
        entered = threading.Event()
        resumed = threading.Event()
        def slow(audio):
            if len(audio) and not entered.is_set():
                entered.set()
                self.assertTrue(resumed.wait(2))
        backend.accept_audio.side_effect = slow
        result = []
        runner = threading.Thread(target=lambda: result.append(session.run(recorder, backend, hotwords="", noise_suppression=False)))
        runner.start()
        self.assertTrue(entered.wait(1))
        time.sleep(0.15)
        self.assertFalse(recorder.is_recording)
        self.assertTrue(runner.is_alive(), "Recognition should still be draining")
        resumed.set()
        runner.join(2)
        self.assertFalse(runner.is_alive())
        self.assertEqual(result[0][0], "text")

    def test_five_minute_limit_is_enforced_by_capture_not_decoder(self):
        session = DictationSession(1, max_seconds=0.05)
        recorder = StreamingRecorder(session, seconds=0.3, release_after=None)
        backend = Mock()
        backend.accept_audio.side_effect = lambda audio: time.sleep(0.12) if len(audio) else None
        backend.finish_session.return_value = "complete"
        session.run(recorder, backend, hotwords="", noise_suppression=False)
        self.assertEqual(session.stop_reason, StopReason.DURATION_LIMIT)
        self.assertEqual(DictationSession(2).max_seconds, 300)

    def test_finalization_timeout_retains_recording_and_interrupts_worker(self):
        session = DictationSession(1, finalization_timeout=0.04)
        recorder = StreamingRecorder(session, seconds=0.3, release_after=0.01)
        backend = Mock()
        resumed = threading.Event()
        backend.accept_audio.side_effect = lambda audio: resumed.wait(2) if len(audio) else None
        backend.interrupt.side_effect = resumed.set
        with self.assertRaisesRegex(IncompleteRecording, "too long"):
            session.run(recorder, backend, hotwords="", noise_suppression=False)
        self.assertEqual(session.stop_reason, StopReason.TIMEOUT)
        self.assertTrue(session.audio_queue.retained())
        backend.interrupt.assert_called()
        backend.finish_session.assert_not_called()

    def test_retained_audio_replays_without_opening_microphone(self):
        session = DictationSession(1)
        chunks = [(np.ones(1600, dtype=np.float32), 16000)] * 4
        backend = Mock()
        backend.finish_session.return_value = "recovered"
        text, duration = session.run(ReplayRecorder(chunks, session), backend, hotwords="", noise_suppression=False)
        self.assertEqual((text, duration), ("recovered", 0.4))

    def test_recorder_storage_is_bounded_even_if_controller_stalls(self):
        recorder = PushToTalkRecorder(RecorderConfig(max_seconds=0.1, retain_audio=False))
        recorder._capturing = True
        received = []
        recorder.on_audio_chunk = lambda audio, rate: received.append(len(audio))
        for _ in range(50):
            recorder._on_audio(np.ones((160, 1), dtype=np.float32), 160, None, SimpleNamespace(input_overflow=False))
        self.assertEqual(sum(received), 1600)
        self.assertEqual(recorder._frames, [])

    def test_injected_keys_and_repeats_do_not_create_extra_actions(self):
        key = PushToTalkHotkey("right_ctrl", Mock(), Mock())
        key._handle_press(KEYS["right_ctrl"], injected=True)
        self.assertFalse(key.pressed)
        key._handle_press(KEYS["right_ctrl"])
        key._handle_press(KEYS["right_ctrl"])
        key._handle_release(KEYS["right_ctrl"], injected=True)
        self.assertTrue(key.pressed)
        key._handle_release(KEYS["right_ctrl"])
        self.assertEqual([key._events.get_nowait(), key._events.get_nowait()], ["press", "release"])
        key.on_press.assert_not_called()
        key.on_release.assert_not_called()
