@echo off
cd /d "%~dp0"
python -c "from voiceprompt.startup import set_startup; set_startup(False); print('Automatic startup disabled. To uninstall the installed app, use Windows Settings > Apps > VoicePrompt.')"
pause
