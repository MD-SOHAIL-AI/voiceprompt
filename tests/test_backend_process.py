import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from voiceprompt.backend_process import ManagedTranscriber
from voiceprompt.config import Settings


class BackendProcessTests(unittest.TestCase):
    def test_stale_connection_failure_cannot_interrupt_a_replacement(self):
        worker = ManagedTranscriber(Settings())
        old, replacement = Mock(), Mock()
        worker._connection = replacement
        with patch.object(worker, "interrupt") as interrupt:
            worker._interrupt_connection(old)
            interrupt.assert_not_called()

    def test_ten_ms_frames_are_batched_without_losing_final_samples(self):
        worker = ManagedTranscriber(Settings(backend="nemotron"))
        with patch.object(worker, "_exchange", return_value="all words") as exchange:
            worker.begin_session()
            audio = np.arange(16007, dtype=np.float32)
            for offset in range(0, len(audio), 160):
                worker.accept_audio(audio[offset:offset + 160])
            self.assertEqual(worker.finish_session(), "all words")
            self.assertEqual(worker.finish_session(), "")
        sent = [c.args[1].copy() for c in exchange.call_args_list if c.args[0] == "accept_audio"]
        self.assertEqual([len(a) for a in sent], [1600] * 10 + [7])
        np.testing.assert_array_equal(np.concatenate(sent), audio)
        self.assertEqual([c.args[0] for c in exchange.call_args_list][-1], "finish_session")

    def test_abort_clears_pending_audio_before_the_next_session(self):
        worker = ManagedTranscriber(Settings())
        with patch.object(worker, "_exchange", return_value="fresh") as exchange:
            worker.begin_session()
            worker.accept_audio(np.ones(71, dtype=np.float32))
            worker.abort_session()
            worker.begin_session()
            worker.accept_audio(np.full(23, 2, dtype=np.float32))
            worker.finish_session()
        sent = [c.args[1] for c in exchange.call_args_list if c.args[0] == "accept_audio"]
        self.assertEqual(len(sent), 1)
        np.testing.assert_array_equal(sent[0], np.full(23, 2, dtype=np.float32))

    def test_source_launch_monitors_the_model_interpreter_not_venv_redirector(self):
        worker = ManagedTranscriber(Settings())
        parent, child = Mock(), Mock()
        child.fileno.return_value = 123
        with patch("voiceprompt.backend_process.mp.Pipe", return_value=(parent, child)), \
             patch("voiceprompt.backend_process.os.set_handle_inheritable"), \
             patch("voiceprompt.backend_process.subprocess.Popen") as start:
            worker._start()
        command = start.call_args.args[0]
        self.assertEqual(command[0], getattr(sys, "_base_executable", sys.executable))
        self.assertEqual(command[1], "-c")
        self.assertIn("run_worker(123)", command[2])
        self.assertIn("sys.path", command[2])

    def test_process_exit_is_a_recoverable_error(self):
        worker = ManagedTranscriber(Settings())
        with patch("voiceprompt.backend_process.subprocess.Popen", wraps=subprocess.Popen) as start:
            worker._start()
        process = worker._process
        process.terminate()
        process.wait(timeout=10)
        with self.assertRaisesRegex(RuntimeError, "worker stopped"):
            worker._exchange("describe", timeout=3)
        self.assertIsNone(worker._process)
        self.assertEqual(worker.loaded_model, "")

    def test_interrupt_terminates_and_reaps_the_worker(self):
        worker = ManagedTranscriber(Settings())
        worker._start()
        process = worker._process
        worker.interrupt()
        self.assertIsNotNone(process.poll())
        self.assertIsNone(worker._connection)
        worker.interrupt()
