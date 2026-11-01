"""Exercise the Windows release gates without a real private key or trust changes."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(os.name == "nt", "Windows release tooling")
class WindowsSigningTests(unittest.TestCase):
    def test_signing_and_release_gates(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        self.assertIsNotNone(shell, "PowerShell is required for Windows release checks")
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "RemoteSigned", "-File",
             str(root / "tests" / "windows_signing_checks.ps1")],
            cwd=root, capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Windows signing checks passed", result.stdout)
