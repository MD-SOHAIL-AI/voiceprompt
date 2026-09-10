@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw VoicePrompt.pyw
) else (
  start "" python VoicePrompt.pyw
)
