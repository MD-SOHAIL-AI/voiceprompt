@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" VoicePrompt.pyw
  exit /b
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw VoicePrompt.pyw
) else (
  start "" python VoicePrompt.pyw
)
