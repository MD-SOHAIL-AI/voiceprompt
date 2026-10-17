# VoicePrompt

Local voice typing and daily focus tools for Windows 10/11 x64.

Hold **Right Ctrl**, speak, then release. VoicePrompt finishes the complete recording and pastes the text once. Speech recognition runs locally; optional cloud text cleanup is off by default.

## Download and install

Get the Windows Setup executable from [GitHub Releases](https://github.com/MD-SOHAIL-AI/voiceprompt/releases). Install it for your Windows account, open VoicePrompt, and follow the microphone setup steps. Python and terminal commands are not required for the packaged app.

The 0.4.1 build is a preview. An unsigned preview is labelled in its release notes; signing support is included in the build script. Models download separately on first preparation. Setup shows progress and supports cancellation and retry; cached models work offline.

Uninstall from **Windows Settings → Apps → Installed apps → VoicePrompt**. The uninstaller closes the installed app and speech workers, removes installed files, shortcuts, and VoicePrompt startup entries, and keeps your settings, history, tasks, and shared model cache. A downloaded installer or a developer's source/build folders remain until you remove them yourself. The `Uninstall VoicePrompt Startup.bat` file only disables automatic startup; it does not uninstall the app.

If you used the 0.4.0 uninstaller while VoicePrompt was running and files remain, install 0.4.1 into the same folder, then uninstall again. This repairs the installation record so the fixed uninstaller can remove those files.

## Voice typing

1. Choose a microphone, use **Check microphone**, then select **Prepare model and microphone**.
2. Wait for **Ready to dictate**.
3. Put the cursor in the destination application.
4. Hold Right Ctrl, speak, and release. Settings also offers press-to-start/stop mode and alternative keys.
5. The final text appears at the cursor and in VoicePrompt. If the active window changed, use **Copy text** to choose the destination yourself.

Recordings support five minutes, with an elapsed timer and a warning during the last ten seconds. A 180 ms release tail preserves final syllables. When recognition falls behind, capture continues and the indicator says it is catching up. Microphone failures, recognition timeouts, and duration limits have explicit messages.

Failed recognition can be retried from memory. This audio is cleared when recovered, discarded, replaced by another recording, or on exit; it is never automatically written to disk. Audio with microphone frame drops is never pasted as a complete recording. Cancel ends the session without inserting text.

## What is included

- Dictation, local transcript history, custom dictionary, microphone setup, tray, and a floating status indicator.
- Existing Whisper, Moonshine, Parakeet, and Nemotron recognition options. New profiles use Whisper base.en on CPU; existing choices are preserved.
- Tasks with notes and reminders; activity timers of any duration; configurable Pomodoro cycles.
- One-time and repeating alarms, dismiss/snooze reminders, and a pending-reminders inbox.
- Codeforces, LeetCode, CodeChef, and AtCoder contest schedules. Codeforces needs no key; other platforms use your CLIST credentials through **Contests → Connect CLIST**.
- Settings for sounds, startup, clipboard restoration, history limits, and optional OpenRouter/Gemini text cleanup.

Timers and planner data work offline. Alarm delivery requires VoicePrompt to be running and Windows awake. Closing the main window keeps the tray running. Choose **Quit** from the tray or app menu to exit.

## Data and privacy

Settings, history, planner data, runtime caches, and bounded diagnostics live under `%LOCALAPPDATA%\VoicePrompt`. Existing data stays in place; configuration migration and the first desktop planner upgrade create backups. Uninstall preserves user data and cached models.

Audio remains local. Enabling cloud cleanup explicitly sends completed transcript text to the selected provider. Cleanup and CLIST keys use Windows Credential Manager, separate from JSON settings and SQLite. Source launches also support the environment variables documented in `.env.example`; never include a real `.env` in a release.

History contains transcript text on this device. Set its limit to zero to disable future persistence, or use **Clear history**. Diagnostic metrics contain timestamps, duration, backlog, stop reason, engine, and outcome, without transcript text or audio. No telemetry is uploaded automatically.

## Run from source

Use 64-bit Python 3.10 on Windows for the validated build environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-lock.txt
.\Start VoicePrompt.bat
```

The normal runtime dependencies are in `requirements.txt`. `requirements-noise.txt` enables optional RNNoise; keep it disabled unless it improves your recognition results. The lock file records the tested Windows build environment.

## Structure

- **Presentation:** `desktop.py` uses PySide6/Qt Widgets; `ui.py` provides thread-safe controller adapters. Legacy Tk screens remain as reference source and regression tests, and are excluded from the packaged app.
- **Controller:** `main.py` owns session lifecycle, settings, insertion, and recovery. Shared states and stop reasons live in `state.py`.
- **Audio and recognition:** `recorder.py`, `session.py`, and `backend_process.py` separate capture from potentially slow recognition. One persistent, isolated process owns the selected model.
- **Services:** existing planner, contest, history, credentials, and storage modules retain their data formats.
- **Release:** `packaging/` defines the bundle and installer; `scripts/build_windows.ps1` builds and validates them. CI prepares draft previews from version tags.

## Test and build

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
.\.venv\Scripts\python scripts/preview_desktop.py
.\scripts\build_windows.ps1
```

The build script needs Inno Setup 6, either under `.tools\inno` or supplied with `-InnoCompiler`. Supply `-SignThumbprint` with your certificate identity and Windows SDK signtool to sign the application and installer. Outputs go to `release/`, including SHA-256 checksums. See [release instructions](docs/releasing.md) for publishing and clean-machine acceptance.

The build self-check loads Qt and launches each speech worker without accessing personal settings, microphone, hooks, or model downloads. It verifies packaging, rather than speech accuracy.

For a five-minute offline endurance replay of bundled licensed public speech:

```powershell
.\.venv\Scripts\python scripts/verify_endurance.py --seconds 300 --backend nemotron
```

This requires the selected model/runtime to be cached. It measures replay performance, not physical-key handling, microphone capture, clipboard delivery, or recognition accuracy.

## Earlier measurements and licensing

The [performance review](docs/performance-review.md), [Nemotron implementation](docs/nemotron-upgrade.md), [Parakeet implementation](docs/parakeet-upgrade.md), and [model comparison](docs/model-comparison-2026-10.md) document the earlier pipeline and laptop measurements. Their two-second-queue and Tk descriptions are historical; this README describes the current app.

Application code is [MIT licensed](LICENSE). Dependencies and model weights retain their own terms; see [third-party notices](THIRD_PARTY_NOTICES.md) and the licenses directory in packaged builds.
