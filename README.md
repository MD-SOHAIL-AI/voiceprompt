# VoicePrompt

Local voice typing and daily focus tools for Windows 10/11 x64.

Hold **Right Ctrl**, speak, then release. VoicePrompt finishes the complete recording and pastes the text once. Speech recognition and transcript processing run locally. No AI API keys are needed.

## Download and install

Get the Windows Setup executable from [GitHub Releases](https://github.com/MD-SOHAIL-AI/voiceprompt/releases). Install it for your Windows account, open VoicePrompt, and follow the microphone setup steps. Python and terminal commands are not required for the packaged app.

The 0.6.0 release candidate adds local-only processing, bounded recovery and transport, safer clipboard handling, phrase decoding, and new recording clicks. See the [candidate notes](docs/release-notes-0.6.0.md) for verification and outstanding production gates.

The 0.5.1 desktop redesign is available as an [unsigned Windows preview](https://github.com/MD-SOHAIL-AI/voiceprompt/releases/tag/v0.5.1-preview.1). See the [release notes](docs/release-notes-0.5.1.md) for features, validation and remaining manual hardware checks. Models download separately on first preparation; cached models work offline. Main-branch pushes do not automatically publish releases.

Windows can show **Windows protected your PC** for these unsigned installers.
Publisher signing is not configured yet. See [Windows signing and SmartScreen](docs/windows-signing.md)
for the verified cause, signing setup, and guidance for existing preview downloads.

Uninstall from **Windows Settings → Apps → Installed apps → VoicePrompt**. The uninstaller closes the installed app and speech workers, removes installed files, shortcuts, and VoicePrompt startup entries, and keeps your settings, history, tasks, and shared model cache. A downloaded installer or a developer's source/build folders remain until you remove them yourself. The `Uninstall VoicePrompt Startup.bat` file only disables automatic startup; it does not uninstall the app.

If you used the 0.4.0 uninstaller while VoicePrompt was running and files remain, install 0.4.1 into the same folder, then uninstall again. This repairs the installation record so the fixed uninstaller can remove those files.

## App updates

Version 0.6.1 adds **Check for updates** in Settings and an **Update now** action
when a stable release is available. Downloads are verified before installation;
choose **Restart to update** when ready. Existing users install the first
updater-enabled version manually once. Saved data and cached models are preserved.
Automatic checks can be disabled. Update signatures and GitHub release hosting
require no paid service; Windows publisher signing remains separate.

Maintainers publish updates by pushing a matching version tag after merging to
main. See [update setup and release instructions](docs/app-updates.md).

## Voice typing

In **Settings → Appearance**, choose Light, Dark, or System brightness and a
Black, Forest, Graphite, Ocean, Lavender, or Sand color theme. Black is the default. Changes save automatically
and update both windows. **Show floating island** hides or reveals it;
**Keep island visible** keeps it available while idle. The pin button in the
expanded island offers the same control. The Island transparency slider ranges from Solid to 25% transparent; text and controls remain opaque. With pinning off, active recordings,
timers, alarms and pending reminders still keep the island visible.

1. Choose a microphone, use **Check microphone**, then select **Prepare model and microphone**.
2. Wait for **Ready to dictate**.
3. Put the cursor in the destination application.
4. Hold Right Ctrl, speak, and release. Settings also offers press-to-start/stop mode and alternative keys.
5. The final text appears at the cursor and in VoicePrompt. If the active window changed, use **Copy text** to choose the destination yourself.

Recordings support five minutes, with an elapsed timer and a warning during the last ten seconds. A 180 ms release tail preserves final syllables. When recognition falls behind, capture continues and the indicator says it is catching up. Microphone failures, recognition timeouts, and duration limits have explicit messages.

Failed recognition can be retried from memory. This audio is cleared when recovered, discarded, replaced by another recording, or on exit; it is never automatically written to disk. Audio with microphone frame drops is never pasted as a complete recording. Cancel ends the session without inserting text.

If recognition returns no text, the recording is also kept for **Retry recording**.
If recording keys or modifiers remain held for two seconds after recognition, the
text becomes available to copy and the app can accept another recording.

## What is included

- Dictation, local transcript history, custom dictionary, microphone setup, tray, and a floating status indicator.
- Existing Whisper, Moonshine, Parakeet, and Nemotron recognition options. New profiles use Whisper base.en on CPU; existing choices are preserved.
- Tasks with notes and reminders; activity timers of any duration; configurable Pomodoro cycles.
- One-time and repeating alarms, dismiss/snooze reminders, and a pending-reminders inbox.
- Codeforces, LeetCode, CodeChef, and AtCoder contest schedules. Codeforces needs no key; other platforms use your CLIST credentials through **Contests → Connect CLIST**.
- Soft recording clicks with preview controls, startup preferences, clipboard restoration, and history limits.

Timers and planner data work offline. Alarm delivery requires VoicePrompt to be running and Windows awake. Closing the main window keeps the tray running. Choose **Quit** from the tray or app menu to exit.

## Data and privacy

Settings, history, planner data, runtime caches, and bounded diagnostics live under `%LOCALAPPDATA%\VoicePrompt`. Existing data stays in place; configuration migration and the first desktop planner upgrade create backups. Uninstall preserves user data and cached models.

Audio and transcript processing remain local. Gemini and OpenRouter integrations and key-entry controls have been removed. Upgrading retires VoicePrompt's old provider credentials from Windows Credential Manager; a failed removal can be retried in Settings. Model preparation can download model files, and contest schedules use their existing online services. CLIST credentials remain in Windows Credential Manager, separate from settings and SQLite.

History contains transcript text on this device. Set its limit to zero to disable future persistence, or use **Clear history**. Diagnostic metrics contain timestamps, duration, backlog, stop reason, engine, and outcome, without transcript text or audio. No telemetry is uploaded automatically.

Automatic app update checks contact GitHub for release metadata and can be disabled
in Settings. Installers download only when you choose Update now. Audio,
transcripts, and diagnostic logs are not included in update requests.

## Run from source

Use 64-bit Python 3.11 on Windows for the build environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-lock.txt
cd desktop
npm ci
npm run tauri -- dev
```

Native development also requires Node 24, Rust stable, Microsoft C++ Build Tools with a Windows SDK, and the Microsoft WebView2 Runtime. `Start VoicePrompt.bat` opens a staged or installed native build. The previous Qt source interface is available with `python VoicePrompt.pyw --legacy-qt` for recovery. See [desktop development](desktop/README.md).

The normal runtime dependencies are in `requirements.txt`. `requirements-noise.txt` enables optional RNNoise; keep it disabled unless it improves your recognition results. The lock file records the tested Windows build environment.

## Structure

- **Presentation:** `desktop/src` contains React/TypeScript, shared state, forms and the floating island. `desktop/src-tauri` owns native windows, the tray, process containment and restricted external links. Qt/Tk presentation is excluded from the new package.
- **Controller:** `main.py` owns session lifecycle, settings, insertion, and recovery. Shared states and stop reasons live in `state.py`.
- **Audio and recognition:** `recorder.py`, `session.py`, and `backend_process.py` separate capture from potentially slow recognition. One persistent, isolated process owns the selected model.
- **Services:** `desktop_sidecar.py` adapts the existing controller, planner, contest, history, credentials and storage services through bounded JSON lines. Both native windows use one engine.
- **Release:** `packaging/` defines the engine and per-user installer. Routine CI tests without publishing; stable version tags use `scripts/build_update_release.py` to build and verify update-signed releases.

## Test and build

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
.\.venv\Scripts\python scripts/check_engine_bridge.py
cd desktop
npm ci
npm run test
npm run build
cd ..
.\scripts\build_desktop.ps1 -AllowUnsignedPreview
```

The build script needs Inno Setup 6, either under `.tools\inno` or supplied with `-InnoCompiler`. Public release builds require `-SignThumbprint` with a trusted certificate identity; they sign and verify the desktop, speech engine, installer and uninstaller. `-AllowUnsignedPreview` explicitly builds a test installer with an `unsigned-preview` filename. Outputs include SHA-256 checksums and a signing report. See [signing setup](docs/windows-signing.md) and [release instructions](docs/releasing.md).

The build self-check launches the Tauri executable and all four frozen speech workers without personal settings, microphone, hooks or model downloads. Separate WebView2 integration checks exercise the actual packaged engine using a disposable profile. These checks verify packaging and workflows; speech accuracy and physical microphone/global-key behavior require manual acceptance.

For a five-minute offline endurance replay of bundled licensed public speech:

```powershell
.\.venv\Scripts\python scripts/verify_endurance.py --seconds 300 --backend nemotron
```

This requires the selected model/runtime to be cached. It measures replay performance, not physical-key handling, microphone capture, clipboard delivery, or recognition accuracy.

## Earlier measurements and licensing

The [performance review](docs/performance-review.md), [Nemotron implementation](docs/nemotron-upgrade.md), [Parakeet implementation](docs/parakeet-upgrade.md), and [model comparison](docs/model-comparison-2026-10.md) document the earlier pipeline and laptop measurements. Their two-second-queue and Tk descriptions are historical; this README describes the current app.

Application code is [MIT licensed](LICENSE). Dependencies and model weights retain their own terms; see [third-party notices](THIRD_PARTY_NOTICES.md) and the licenses directory in packaged builds.
