# Voice Prompt Desktop V2

Voice Prompt V2 is the production desktop migration of Voice Prompt: a Tauri 2 + React shell that reuses the hardened Python dictation engine.

## Current hardening status

Implemented and reviewable:
- clean main app plus separate transparent overlay
- real microphone envelope events from the Python recorder
- local Whisper transcription through the existing hardened engine
- target-window-aware paste and clipboard restoration
- JSON-lines native bridge with bounded command/event sizes
- history/privacy UI, provider/model UI, performance and WER/CER UI
- Windows CI for Python, TypeScript and Rust validation
- close-to-tray/single-instance native lifecycle foundation

Release gates that remain intentionally disabled rather than faked:
- cloud transcription/cleanup execution from the sidecar
- production credential/provider commands in the Rust layer
- packaged sidecar resource wiring and installer smoke test
- global-hotkey ownership migration from the legacy process
- signed updater/release pipeline

The UI can be developed now, but this branch remains a draft until those gates are implemented and CI passes.

## Development

Prerequisites: Node.js 22+, Rust stable, Python 3.12, WebView2.

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-desktop.txt
cd desktop
npm ci
npm run tauri dev
```

In debug builds the Rust bridge starts:

```text
python -u -m voiceprompt.desktop_sidecar
```

For a packaged/native engine executable, set `VOICEPROMPT_ENGINE` to an explicit trusted executable path. The build helper can create the executable with:

```powershell
cd desktop
npm run build:engine
```

## Security and privacy invariants

- Local mode keeps captured audio on-device.
- Cloud mode is not silently substituted for Local mode.
- History is off by default.
- The original foreground window is captured before recording and paste is refused if it cannot be safely restored.
- Clipboard restoration is conditional and will not overwrite a newer clipboard value.
- Provider secrets must never be persisted in React state, localStorage, SQLite, logs, or history.
- Accuracy is reported only from reference-backed WER/CER measurements.
- Provider pricing/free-tier labels must come from provider metadata; unknown pricing is shown as provider quota/unknown rather than guessed.

## Production build

The sidecar and installer are separate release gates. Build the engine first, then wire/copy the verified binary into the release bundle as part of the signed release workflow. Do not treat a frontend-only Tauri build as a production installer.

```powershell
cd desktop
npm run build:engine
npm run build
```

The draft PR should stay unmerged until the full Windows release workflow validates the packaged executable and installer.
