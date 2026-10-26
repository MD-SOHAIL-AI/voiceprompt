@echo off
cd /d "%~dp0"
python -c "from voiceprompt.startup import set_startup; set_startup(True); print('VoicePrompt will start automatically on login.')"
pause
