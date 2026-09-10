@echo off
cd /d "%~dp0"
python -c "from voiceprompt.startup import set_startup; set_startup(False); print('Voice Prompt startup entry removed.')"
pause
