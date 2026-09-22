@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "from voiceprompt.startup import set_startup; set_startup(True); print('Voice Prompt will start automatically on login.')"
) else (
  python -c "from voiceprompt.startup import set_startup; set_startup(True); print('Voice Prompt will start automatically on login.')"
)
pause
