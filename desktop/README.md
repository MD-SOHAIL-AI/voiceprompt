# Voice Prompt Desktop V2

Voice Prompt V2 is a Tauri 2 + React desktop shell around the existing Voice Prompt engine.

## Product shape

- Main desktop app: Home, History, Models, Providers, Performance, Dictionary, Settings.
- Floating overlay: separate transparent always-on-top Tauri window driven by live microphone levels.
- Local engine: existing Python recorder, faster-whisper / whisper.cpp router, safe paste, replacements, and sound feedback.
- Cloud transcription: Groq, Gemini, OpenRouter, and custom OpenAI-compatible speech endpoints.
- Cloud cleanup: Groq, Gemini, OpenRouter, NVIDIA NIM, and custom OpenAI-compatible chat endpoints.
- Secrets: stored in the operating-system credential vault through Rust `keyring`; saved API keys are not returned to React.
- History/metrics: SQLite with per-prompt latency, provider/model, cost when reported by the provider, and optional WER/CER scoring against a reference transcript.

## Development

Prerequisites on Windows:

- Node.js 20+
- Rust toolchain compatible with Tauri 2
- Python 3.11+
- WebView2 Runtime

Install frontend dependencies:

```powershell
cd desktop
npm install
```

Install the Python engine dependencies from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-desktop.txt
```

Run Tauri in development:

```powershell
cd desktop
npm run tauri dev
```

During development Rust starts the engine with:

```text
python -u -m voiceprompt.desktop_sidecar
```

You can override the engine executable and working directory with:

```text
VOICEPROMPT_ENGINE
VOICEPROMPT_ENGINE_CWD
```

## Production build

The Tauri build hook runs `scripts/build-engine.ps1` first. It packages the Python sidecar as:

```text
desktop/src-tauri/bin/voiceprompt-engine.exe
```

Then Tauri bundles that executable as an application resource and builds MSI/NSIS installers.

```powershell
cd desktop
npm run tauri build
```

## Provider behavior

Provider/model catalogs are discovered dynamically.

- Groq: `/openai/v1/models`; Whisper-class models are used for transcription.
- OpenRouter: model catalog is filtered by `output_modalities=transcription` or `text` depending on the stage.
- Gemini: `v1beta/models`; API keys are sent using `x-goog-api-key`.
- NVIDIA NIM: OpenAI-compatible hosted/custom model catalog for cleanup. Transcription is intentionally not assumed for the generic NIM endpoint.
- Custom: user-supplied OpenAI-compatible base URL.

The UI marks a model **Free** only when the live provider catalog reports zero pricing. Models whose billing cannot be inferred safely are labeled **Provider quota** instead of guessing.

## Engine routing

`Local` always uses the local ASR engine.

`Cloud` requires the selected provider credential and uses the selected cloud transcription model.

`Auto` attempts the selected cloud route and falls back to local Whisper if the provider is unavailable or the request fails.

Optional cleanup is a separate pipeline stage and can use a different provider/model than transcription.

## Privacy

- Local mode keeps audio on-device.
- Cloud mode sends captured audio only to the selected transcription provider.
- Cleanup sends transcript text only when explicitly enabled.
- Provider credentials live in the OS credential vault.
- Prompt history can be disabled; when enabled it is stored locally in SQLite.

## Privacy default

Prompt history is off by default in the native desktop runtime. Users can opt in from Settings; retention is then enforced automatically. Provider API keys are stored in the OS credential vault and are never persisted in the React frontend or SQLite.
