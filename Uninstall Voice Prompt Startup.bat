@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "from voiceprompt.startup import set_startup; set_startup(False); print('Voice Prompt startup entry removed.')"
) else (
  python -c "from voiceprompt.startup import set_startup; set_startup(False); print('Voice Prompt startup entry removed.')"
)
pause
