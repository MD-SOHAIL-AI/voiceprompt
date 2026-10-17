import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from voiceprompt.backend_process import ManagedTranscriber
from voiceprompt.config import Settings


class BackendProcessTests(unittest.TestCase):
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
