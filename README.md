# Voice Prompt

Voice Prompt is a lightweight Windows push-to-talk dictation utility for AI prompts, coding, notes, browsers, editors, and terminals.

```text
hold hotkey -> activation tone -> speak -> local ASR -> release -> deactivation tone -> optional cleanup -> safe paste
```

## Default setup

The default recognizer is now **multilingual Whisper `base`** on CPU/int8 through `faster-whisper`. Language detection is automatic unless a language is selected manually.

For lower native-runtime overhead, Voice Prompt also supports an optional **whisper.cpp** backend. Configure the path to `whisper-cli.exe` and a compatible quantized multilingual Whisper model in Settings. `Auto` uses whisper.cpp when both paths are valid and otherwise falls back to faster-whisper.

Recommended modes for an 8 GB Windows laptop:

- Fast/default: `base`, multilingual, CPU/int8
- Accuracy: `small`, multilingual, CPU/int8
- Native/experimental: whisper.cpp with a quantized multilingual model

## Recording sound feedback

Sound feedback is enabled by default so you can use Voice Prompt without looking at the floating pill:

- **Hotkey activates recording:** a short ascending two-tone cue plays.
- **Hotkey is released / recording stops:** a short descending two-tone cue plays.
- The activation cue finishes **before the microphone opens**, so Voice Prompt does not transcribe its own notification sound.
- The deactivation cue plays only **after the microphone is fully closed**, including the final-phoneme grace window.
- The cues are available in both push-to-talk and toggle recording modes.
- Sound feedback can be disabled from **Settings** or directly from the tray menu.
- If Windows cannot play the tone, dictation continues normally; sound feedback never blocks the core workflow.

## Reliability and privacy improvements

- Final-phoneme release grace is captured correctly.
- Maximum recording duration prevents forgotten toggle recordings from consuming memory indefinitely.
- The floating waveform is driven by real microphone RMS level.
- Paste is tied to the window where dictation started. If the target cannot safely regain focus, automatic paste is skipped and **Retry last transcription** remains available.
- Clipboard restoration only happens when Voice Prompt still owns the clipboard value, so a newer user copy is never overwritten.
- Transcription history is **off by default**. It can be enabled in Settings and cleared from the tray.
- Cloud cleanup is optional/off by default and results pass integrity checks for numbers, URLs, email addresses, and common technical tokens.
- Disabling/re-enabling cloud cleanup remembers the previously selected provider.
- Dictionary replacements work with punctuation-heavy technical terms such as `C++`.
- Settings use the same Tk UI thread as the floating pill rather than creating a second Tk root on a worker thread.
- Startup scripts prefer the project `.venv`.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Run:

```powershell
.\Start Voice Prompt.bat
```

The first run can take longer while Whisper is downloaded and cached.

## Usage

1. Place the cursor in the target text field.
2. Hold **Right Ctrl**.
3. Wait for the short rising activation cue, then speak.
4. Release **Right Ctrl**.
5. Hear the short falling deactivation cue.
6. Voice Prompt transcribes locally and pastes back into the original target window.

Very short accidental taps are ignored. Toggle mode is available in Settings.

## Multilingual settings

The default language is `auto`. Common quick choices in the UI include English (`en`), Tamil (`ta`), Hindi (`hi`), Telugu (`te`), Malayalam (`ml`), and Kannada (`kn`). The underlying multilingual Whisper model supports additional languages; `auto` is recommended for general use.

## whisper.cpp backend

Voice Prompt does not bundle native binaries or model weights. To use whisper.cpp:

1. Build or download a Windows `whisper-cli.exe` from whisper.cpp.
2. Obtain a compatible quantized multilingual Whisper model, preferably `base` or `small` for low-RAM laptops.
3. Open **Voice Prompt Settings**.
4. Set **ASR backend** to `whisper_cpp` or `auto`.
5. Set the **whisper.cpp exe** and **whisper.cpp model** paths.
6. Choose an appropriate thread count.

If `auto` is selected and those paths are unavailable, Voice Prompt continues with faster-whisper.

## Optional cloud cleanup

```powershell
Copy-Item .env.example .env
```

Then add only the key for the provider you intend to use:

```text
GEMINI_API_KEY=
OPENROUTER_API_KEY=
```

Cloud cleanup has a hard timeout and always falls back to the local transcript on provider failure or integrity-check failure.

## Start on boot

```powershell
.\Install Voice Prompt Startup.bat
```

Remove it with:

```powershell
.\Uninstall Voice Prompt Startup.bat
```

## Tests

```powershell
python -m unittest discover -s tests -v
```

A Windows GitHub Actions workflow runs the test suite on pushes and pull requests.

## Packaging

For daily Windows use, an onedir PyInstaller build is recommended:

```powershell
pip install pyinstaller
pyinstaller --noconsole --name VoicePrompt --onedir --collect-all faster_whisper --collect-all ctranslate2 voiceprompt\main.py
```

## Local files

Configuration and optional transcription history are stored under the user's Windows app config directory, normally:

```text
%APPDATA%\Voice Prompt\
```

API keys remain in `.env`, which is ignored by Git.
