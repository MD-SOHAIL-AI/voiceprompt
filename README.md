# Voice Prompt

A lightweight Windows push-to-talk voice typing app inspired by BridgeVoice, TalkType, and faster-whisper-hotkey.

Workflow:

```text
hold Right Ctrl -> speak -> release -> local faster-whisper transcription -> optional cloud cleanup -> paste
```

Normal launch:

```text
Double-click Start Voice Prompt.bat
```

The app is designed for Windows 10/11 laptops without a dedicated GPU. It defaults to `base.en`, CPU, `int8` inference, and a modest accuracy setting so it is still quick but more reliable than the fastest tiny model.

## Features

- Global push-to-talk hotkey
- Default hotkey: hold Right Ctrl
- Local transcription with `faster-whisper`
- Reuses one loaded Whisper model during the app session
- Prevents duplicate app instances from transcribing the same recording multiple times
- Warms the model in the background at startup by default
- Uses dictionary terms as Whisper vocabulary hints
- Keeps a short release grace period so final syllables are not clipped
- Optional silence filtering to reduce hallucinations and wasted decoding
- Clipboard paste injection into the currently focused app
- Clipboard restore after paste when possible
- Tiny always-on-top alive pill
- Stable tray icon with status: idle, loading model, ready, recording, transcribing
- Settings window for hotkey, model, language, cleanup, startup, and replacements
- Push-to-talk mode and toggle-recording mode
- Accuracy setting from 1 to 5
- Local transcription history
- Retry last transcription from the tray
- Optional OpenRouter or Gemini cleanup, disabled by default
- OpenRouter free-model routing with a hard timeout and local fallback
- Custom dictionary replacements, for example `chat g p t=ChatGPT`
- Includes vocabulary hints for Brahmshosh, Claude Code, OpenRouter, and embedded systems

## Project Structure

```text
voiceprompt/
  __init__.py
  main.py
  config.py
  hotkeys.py
  recorder.py
  transcriber.py
  injector.py
  ui.py
  history.py
  cleanup.py
  replacements.py
  startup.py
README.md
requirements.txt
.env.example
```

Settings and history are stored under your Windows app config directory, usually:

```text
%APPDATA%\Voice Prompt\
```

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

Optional cloud cleanup:

```powershell
Copy-Item .env.example .env
```

Then set:

```text
GEMINI_API_KEY=your_key_here
OPENROUTER_API_KEY=your_key_here
```

Only the key for the provider you select is needed. In Settings, choose `openrouter` with
`openrouter/free` for zero-cost model routing, or choose `gemini` and enter a Gemini model.
Cloud cleanup is off by default and local dictation works without any API key. Free OpenRouter
models can be rate-limited or temporarily unavailable, so Voice Prompt returns the local text
unchanged when the request fails or exceeds the configured timeout.

## Run

Easy mode:

```powershell
.\Start Voice Prompt.bat
```

Or run from PowerShell:

```powershell
python -m voiceprompt.main
```

The first run may take longer because faster-whisper downloads and caches the model. After startup:

1. Put your cursor in Notepad, a browser, ChatGPT, VS Code, a terminal, or another text field.
2. Hold Right Ctrl.
3. Speak.
4. Release Right Ctrl.
5. The transcript is pasted at the cursor.

Use the tray icon to open settings, retry the last transcription, toggle cleanup, toggle startup on boot, or quit.

The model warms up on a worker thread at startup so the first real dictation is faster. This can
be disabled in Settings, and **Warm up model** remains available from the tray.

The floating pill is always on top so you can see the app is alive:

- gray/white: idle
- green: ready
- red moving bars: recording
- blue moving bars: transcribing
- purple moving bars: cloud cleanup
- amber moving bars: loading the model

Drag the pill anywhere on screen. Voice Prompt remembers its position.

## Start on Boot

Use one of these options once:

```powershell
.\Install Voice Prompt Startup.bat
```

Or open the tray/settings UI and enable **Start on boot**.

To remove it from startup:

```powershell
.\Uninstall Voice Prompt Startup.bat
```

## Packaging for Windows

Install PyInstaller:

```powershell
pip install pyinstaller
```

Single-file build:

```powershell
pyinstaller --noconsole --name VoicePrompt --onefile --collect-all faster_whisper --collect-all ctranslate2 voiceprompt\main.py
```

Recommended folder build for faster startup:

```powershell
pyinstaller --noconsole --name VoicePrompt --onedir --collect-all faster_whisper --collect-all ctranslate2 voiceprompt\main.py
```

The `--onedir` build is usually better for daily use because it starts faster and avoids some one-file extraction overhead.

## Low-RAM Laptop Recommendations

- Keep the default model at `base.en` for better accuracy.
- Switch to `tiny.en` only when speed matters more than recognition quality.
- Set Accuracy to `1` for fastest transcription or `3` for the default balanced mode.
- Keep `device=cpu` and `compute_type=int8`.
- Keep cloud cleanup disabled for minimum latency; enable it when punctuation and correction quality matter more.
- Use `openrouter/free` for zero-cost cleanup, but a specific fast model is more predictable when available.
- Prefer short dictation bursts.
- Use `small.en` only if accuracy matters more than RAM and latency.
- Prefer PyInstaller `--onedir` over `--onefile`.
- Keep history bounded; the default is 50 items.
- Avoid webview/dashboard shells for the always-running app. Voice Prompt uses a small tray plus Tk settings window so long transcription work does not freeze the UI.

## Notes

- This is push-to-talk only. It does not continuously listen.
- Text injection uses clipboard paste because it works across browsers, ChatGPT, editors, terminals, and Notepad more reliably than keystroke-by-keystroke typing.
- Very short accidental hotkey taps are ignored.
