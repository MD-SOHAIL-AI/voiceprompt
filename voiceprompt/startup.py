from __future__ import annotations

import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "Voice Prompt"


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def preferred_pythonw() -> Path:
    root = project_root()
    venv_pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
    if venv_pythonw.exists():
        return venv_pythonw
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return pythonw if pythonw.exists() else exe


def executable_command() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() not in {"python.exe", "pythonw.exe"}:
        return f'"{exe}"'

    launcher = preferred_pythonw()
    root_arg = str(project_root()).replace("'", "''")
    launcher_arg = str(launcher).replace("'", "''")
    return (
        'powershell.exe -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass '
        f'-Command "Set-Location -LiteralPath \'{root_arg}\'; & \'{launcher_arg}\' -m voiceprompt.main"'
    )


def set_startup(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, executable_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


def startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False
