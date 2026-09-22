@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" VoicePrompt.pyw
  exit /b 0
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw VoicePrompt.pyw
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    start "" python VoicePrompt.pyw
  ) else (
    echo Python was not found. Create .venv and install requirements first.
    pause
  )
)
