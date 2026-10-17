@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m voiceprompt.evaluate record
if errorlevel 1 goto finished
".venv\Scripts\python.exe" -m voiceprompt.evaluate run --manifest evaluation\voice\manifest.jsonl --noise-comparison --thread-sweep
:finished
pause
