from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import MagicMock

import numpy as np

from voiceprompt.recorder import Recording
from voiceprompt.session import AudioQueue, DictationSession, IncompleteRecording


class SessionTests(unittest.TestCase):
    def test_audio_queued_between_empty_read_and_capture_done_is_drained(self):
        session = DictationSession(1)
        recorder = self.make_recorder(session)
        backend = MagicMock()
        backend.finish_session.return_value = "complete sentence"
        stopped = threading.Event()
        original_get = session.audio_queue.get
        first_read = True

        def delayed_empty_read(timeout=0.02):
            nonlocal first_read
            if first_read:
                first_read = False
                # Simulate an empty read that resumes just after stop delivers
                # the release tail and publishes capture completion.
                self.assertTrue(stopped.wait(1))
                return None
            return original_get(timeout)

        session.audio_queue.get = delayed_empty_read
        session.run(recorder, backend, hotwords="", noise_suppression=False,
                    on_recording_stopped=stopped.set)
        self.assertEqual(sum(len(c.args[0]) for c in backend.accept_audio.call_args_list), 3200)

    def test_capture_starts_before_slow_recognizer_session_setup(self):
        session = DictationSession(1)
        recorder = self.make_recorder(session)
        backend = MagicMock()
        backend.begin_session.side_effect = lambda *_: self.assertTrue(recorder.start.called)
        backend.finish_session.return_value = "all words"
        self.assertEqual(session.run(recorder, backend, hotwords="", noise_suppression=False)[0], "all words")

    def test_duration_bound_handles_variable_callback_sizes(self):
        queue = AudioQueue(max_seconds=2)
        queue.put(np.ones(16000), 16000)
        queue.put(np.ones(16000), 16000)
        queue.put(np.ones(1), 16000)
        with self.assertRaises(IncompleteRecording):
            queue.get()
        self.assertTrue(queue.overflow)

    def test_queue_budget_is_freed_after_consumption(self):
        queue = AudioQueue()
        queue.put(np.ones(16000), 16000)
        queue.get()
        queue.put(np.ones(32000), 16000)
        self.assertFalse(queue.overflow)

    def make_recorder(self, session, overflow=False):
        recorder = MagicMock()
        recorder.sample_rate = 16000
        recorder.input_overflows = 1 if overflow else 0
        recorder.callback_error = ""
        recorder.capture_open_seconds = 0.01
        recorder.input_latency_seconds = 0.01
        recorder.host_api = "Test"
        recorder.is_recording = False

        def start():
            recorder.is_recording = True
            recorder.on_audio_chunk(np.ones(1600, dtype=np.float32), 16000)
            session.request_release()

        def stop(**kwargs):
            recorder.is_recording = False
            recorder.on_audio_chunk(np.ones(1600, dtype=np.float32), 16000)
            return Recording(np.ones(3200, dtype=np.float32), 16000, 0.2)

        recorder.start.side_effect = start
        recorder.stop.side_effect = stop
        return recorder

    def test_release_drains_tail_audio_before_exactly_one_finalization(self):
        session = DictationSession(1)
        recorder = self.make_recorder(session)
        backend = MagicMock()
        backend.finish_session.return_value = "complete sentence"
        text, duration = session.run(recorder, backend, hotwords="MyProject", noise_suppression=False)
        self.assertEqual(text, "complete sentence")
        self.assertEqual(duration, 0.2)
        backend.finish_session.assert_called_once()
        self.assertEqual(sum(len(c.args[0]) for c in backend.accept_audio.call_args_list), 3200)
        self.assertIn("release_to_final_seconds", session.metrics)

    def test_dropped_audio_prevents_final_transcript(self):
        session = DictationSession(1)
        recorder = self.make_recorder(session, overflow=True)
        backend = MagicMock()
        with self.assertRaisesRegex(IncompleteRecording, "dropped"):
            session.run(recorder, backend, hotwords="", noise_suppression=False)
        backend.finish_session.assert_not_called()
        backend.abort_session.assert_called_once()

    def test_release_before_capture_starts_is_ignored(self):
        session = DictationSession(1)
        session.request_release()
        recorder, backend = MagicMock(), MagicMock()
        self.assertEqual(session.run(recorder, backend, hotwords="", noise_suppression=False), ("", 0.0))
        recorder.start.assert_not_called()

    def test_cancel_stops_capture_without_finalizing(self):
        session = DictationSession(1)
        recorder = self.make_recorder(session)
        recorder.start.side_effect = lambda: session.cancel.set()
        backend = MagicMock()
        with self.assertRaisesRegex(IncompleteRecording, "cancelled"):
            session.run(recorder, backend, hotwords="", noise_suppression=False)
        backend.finish_session.assert_not_called()

    def test_unexpected_stream_stop_is_reported_and_not_decoded(self):
        session = DictationSession(1)
        recorder = self.make_recorder(session)
        recorder.capture_failed = True
        backend = MagicMock()
        with self.assertRaisesRegex(IncompleteRecording, "stopped unexpectedly"):
            session.run(recorder, backend, hotwords="", noise_suppression=False)
        backend.finish_session.assert_not_called()
        self.assertTrue(session.metrics["capture_failed"])

    def test_feedback_is_after_capture_start_and_after_stop_before_finalization(self):
        session = DictationSession(1)
        recorder = self.make_recorder(session)
        backend = MagicMock()
        backend.finish_session.return_value = "hello"
        events = []
        def started():
            self.assertTrue(recorder.is_recording)
            events.append("start")
        def stopped():
            self.assertFalse(recorder.is_recording)
            backend.finish_session.assert_not_called()
            events.append("stop")
        session.run(recorder, backend, hotwords="", noise_suppression=False,
                    on_recording_started=started, on_recording_stopped=stopped)
        self.assertEqual(events, ["start", "stop"])

    def test_feedback_failure_cannot_discard_transcription(self):
        session = DictationSession(1)
        recorder = self.make_recorder(session)
        backend = MagicMock()
        backend.finish_session.return_value = "hello"
        feedback = MagicMock(side_effect=RuntimeError("speaker missing"))
        text, _ = session.run(recorder, backend, hotwords="", noise_suppression=False,
                              on_recording_started=feedback, on_recording_stopped=feedback)
        self.assertEqual(text, "hello")
        self.assertEqual(feedback.call_count, 2)

    def test_failed_microphone_and_early_release_produce_no_sound(self):
        for released in (True, False):
            session = DictationSession(1)
            if released:
                session.request_release()
            recorder = self.make_recorder(session)
            recorder.start.side_effect = RuntimeError("microphone unavailable")
            feedback = MagicMock()
            try:
                session.run(recorder, MagicMock(), hotwords="", noise_suppression=False,
                            on_recording_started=feedback, on_recording_stopped=feedback)
            except RuntimeError:
                pass
            feedback.assert_not_called()
