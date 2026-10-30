# VoicePrompt desktop

Tauri 2 hosts the main React/TypeScript window and a separate compact floating
island. Both windows share the existing Python dictation and planner services
through bounded, versioned JSON lines. No HTTP speech server is started.

## Development

Use Windows x64, Python 3.11, Node 24, Rust stable with Microsoft C++ Build Tools
and a Windows SDK, plus the Microsoft WebView2 Runtime.

```powershell
# Repository root
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-lock.txt
cd desktop
npm ci
npm run tauri -- dev
```

Debug builds select `.venv311/Scripts/python.exe` when present (to preserve older
local environments), then `.venv/Scripts/python.exe`, falling back to `python`.
Packaged builds use only `engine/VoicePromptEngine.exe` next to the
native executable. Arbitrary engine executable overrides are unsupported.

For browser-only layout development, use `npm run dev` and open
`http://127.0.0.1:1420/?preview=1`. This explicit mode uses labeled sample data;
microphone access, global shortcuts, provider connections and native actions are
inactive. A plain browser visit never silently impersonates the desktop app.

## Verification and packaging

```powershell
npm run test
npm run build
npx playwright install chromium
node scripts/verify-ui.cjs --preview
# From the root, build the complete native application and installer:
./scripts/build_desktop.ps1 -AllowUnsignedPreview
./scripts/check_native.ps1
```

`check_native.ps1` uses an isolated temporary profile and WebView2 inspection to
exercise the actual packaged engine. It cannot access provider credentials,
change Windows startup, or download speech models. `check_installer.ps1` belongs
in a clean account, since it tests installation and live uninstall.

## Surfaces and privacy

The seven tools remain Dictation, History, Tasks, Focus timer, Alarms, Contests
and Settings. The 112 x 32 DIP island expands to at most 320 x 400 DIP. Focus,
Alarms and Notifications tabs expose quick controls and contest actions.
Reminder previews and sounds wait until recording, recognition and paste finish.

Raw microphone audio remains in the local speech engine. The waveform receives
only a bounded 32-value amplitude envelope. AI processing stays on the device. Legacy cloud credentials are retired on upgrade. Model downloads and optional contest requests remain online; CLIST uses Windows Credential Manager.

The app uses local fonts and code-rendered controls/waveforms. It contains no
remote scripts or analytics. Stable version tags publish verified app updates;
routine main pushes do not. See `docs/app-updates.md`, the root README,
`docs/desktop-redesign.md` and `docs/releasing.md` for acceptance limits.
