from __future__ import annotations

import sys
import os
import winreg
from pathlib import Path


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "VoicePrompt"
LEGACY_APP_NAME = "Voice Prompt"
LEGACY_APP_NAMES = (LEGACY_APP_NAME, "Prompt Voice")


def executable_command() -> str:
    desktop = os.environ.get("VOICEPROMPT_DESKTOP_EXE", "")
    if desktop:
        path = Path(desktop)
        if path.is_absolute() and path.name.lower() == "voiceprompt.exe" and path.is_file():
            return f'"{path}"'
    exe = Path(sys.executable)
    if exe.name.lower() in {"python.exe", "pythonw.exe"}:
        project_root = Path(__file__).resolve().parent.parent
        local_python = project_root / ".venv" / "Scripts" / "pythonw.exe"
        pythonw = local_python if local_python.exists() else exe.with_name("pythonw.exe")
        launcher = pythonw if pythonw.exists() else exe
        root_arg = str(project_root).replace("'", "''")
        launcher_arg = str(launcher).replace("'", "''")
        return (
            'powershell.exe -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass '
            f'-Command "Set-Location -LiteralPath \'{root_arg}\'; & \'{launcher_arg}\' -m voiceprompt.launcher"'
        )
    return f'"{exe}"'


def set_startup(enabled: bool) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, executable_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        for name in LEGACY_APP_NAMES:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass


def startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            for name in (APP_NAME, *LEGACY_APP_NAMES):
                try:
                    winreg.QueryValueEx(key, name)
                    return True
                except FileNotFoundError:
                    pass
            return False
    except FileNotFoundError:
        return False
