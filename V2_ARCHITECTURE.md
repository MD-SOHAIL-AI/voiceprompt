# Voice Prompt V2 Architecture

## Goals

Voice Prompt V2 turns the existing push-to-talk utility into a production-oriented Windows desktop app without discarding the hardened local engine.

### UX principles

1. The floating overlay is the everyday interaction surface.
2. The full app is the control center for history, routing, models, providers, metrics, and customization.
3. The waveform is the visual identity; no decorative lightning logo is required.
4. Recording, transcription, cleanup, success, and error use distinct state colors.
5. Provider/model availability and pricing are discovered dynamically rather than hardcoded when possible.
6. Accuracy is measured with WER/CER against a reference transcript; the app never invents an accuracy percentage.

## Runtime architecture

```text
Global hotkey
    |
    v
Python engine sidecar
    |-- mic capture + real RMS envelope
    |-- local faster-whisper / whisper.cpp
    |-- cloud ASR adapters
    |-- optional cleanup adapters
    |-- focus-safe clipboard injection
    |
    | JSON-lines events/commands over stdio
    v
Tauri / Rust desktop core
    |-- process lifecycle
    |-- SQLite history + metrics
    |-- OS credential vault
    |-- live provider catalogs
    |-- tray + close-to-tray
    |-- overlay window lifecycle
    v
React UI
    |-- Main dashboard
    |-- History
    |-- Models
    |-- Providers
    |-- Performance + WER/CER
    |-- Dictionary
    |-- Settings
    `-- Floating overlay window
```

## Security boundary

React never reads a stored provider secret. The user enters a key once; the value crosses Tauri IPC to a Rust command and is written to the operating-system credential store. React receives only connection state.

When a provider is selected for transcription or cleanup, Rust reads the credential and passes it to the Python engine process in-memory as part of the engine profile. It is not written to SQLite or the frontend state.

## Storage

SQLite tables:

- `app_settings`
- `provider_config` (non-secret endpoint metadata only)
- `transcription_history`
- `accuracy_scores`

Provider API keys are not stored in SQLite.

## Provider adapter matrix

| Provider | Transcription | Cleanup | Catalog |
| --- | --- | --- | --- |
| Local | Yes | No | Static local registry |
| Groq | Yes | Yes | Live `/models` |
| Gemini | Yes | Yes | Live Gemini models API |
| OpenRouter | Yes | Yes | Live filtered model catalog |
| NVIDIA NIM | Deployment-dependent; not assumed | Yes | Live OpenAI-compatible catalog |
| Custom OpenAI-compatible | Yes when endpoint supports audio | Yes | Live `/models` |

## Floating overlay

Separate transparent Tauri window, always on top and excluded from the taskbar.

States:

```text
Ready        neutral compact capsule
Recording    real microphone envelope / green
Transcribing animated processing bars / cyan
Cleaning     animated processing bars / violet
Success      compact confirmation / green
Error        compact warning / red
```

The Python engine emits real normalized microphone levels roughly every 30 ms. The React overlay keeps a rolling window and animates the bar heights with short easing.

## Production packaging

Development uses Python directly. Production packages `voiceprompt.desktop_sidecar` with PyInstaller into `voiceprompt-engine.exe`. Tauri includes it as an application resource and starts it hidden with stdio pipes.

The main window closes to the system tray so the hotkey and floating overlay continue running.

## Privacy default

Prompt history is off by default in the native desktop runtime. Users can opt in from Settings; retention is then enforced automatically. Provider API keys are stored in the OS credential vault and are never persisted in the React frontend or SQLite.
