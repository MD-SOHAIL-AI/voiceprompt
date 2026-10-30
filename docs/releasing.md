# Build and release VoicePrompt

## Validated target

Windows x64, Python 3.11, Node 24, Rust stable/MSVC with a Windows SDK,
Microsoft WebView2 Runtime, PyInstaller 6.22.3 and Inno Setup 6.
The source lock file records the tested environment, including optional RNNoise.
Build on Windows; do not copy a Python virtual environment to users.
The complete installer build downloads the official Microsoft WebView2 bootstrapper
and verifies its Microsoft Authenticode signature before packaging it. Setup offers
the runtime only when absent. That first runtime installation needs internet;
offline machines can preinstall Microsoft's Evergreen Standalone Runtime.
See [Microsoft's deployment guidance](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution).

## Local release

1. Install `requirements-lock.txt` into a dedicated virtual environment.
2. Run `python -m unittest discover -s tests -v` from that environment.
3. Run `scripts/build_windows.ps1 -SignThumbprint <trusted certificate thumbprint>`,
   supplying `-Python` and `-InnoCompiler` as needed. For testing only, explicitly
   use `-AllowUnsignedPreview` instead of signing.
4. Inspect `build/frozen-smoke.json`. Every selected backend must describe itself;
   the release also includes the optional RNNoise native library.
5. The installer, `.sha256` checksum, and `.signing.json` audit appear under
   `release/`. Unsigned test installers have an `-unsigned-preview` filename suffix.
6. Run `scripts/check_installer.ps1` in a clean Windows account. It installs and
   reinstalls with startup enabled and disabled, then uninstalls with a live
   frozen app and speech worker. It checks normal shutdown, all installed files,
   shortcuts, Windows registration, runtime and legacy startup cleanup, unrelated
   startup preservation, and a saved-data marker. Original startup values are
   restored after the test. Evidence is in `build/installer-check.json` and logs.

The folder bundle remains under `dist/VoicePrompt`. It includes the interpreter,
native dependencies, the Tauri executable, frozen Python engine, notices and
local font assets; Qt is excluded and model weights remain separate.

## Signing

See [Windows signing and SmartScreen](windows-signing.md) for identity setup and
exact commands. A public release build requires an installed trusted certificate.
The desktop, engine, installer and embedded uninstaller are signed and timestamped;
signature and checksum failures stop the build. The final signing audit records
actual identities and hashes. `check_installer.ps1` also verifies the installed
executables and uninstaller; use `-AllowUnsignedPreview` only for unsigned tests.

Without an identity, the default build fails before compiling or replacing files.
An explicit `-AllowUnsignedPreview` build is for testing and may trigger SmartScreen.
No signing method guarantees immediate SmartScreen reputation for direct downloads.
Keep private keys and provider credentials outside the repository.

## Clean-machine acceptance

Use a Windows 10/11 x64 VM without Python. Verify:

- Install as a normal user, without administrator access, and launch from Start.
- Choose a microphone, check input, prepare the default model, cancel a download,
  retry, and restart with the network disconnected after caching.
- Dictate in Notepad, a browser text field, and an editor. Check Right/Left Ctrl,
  F8/F9, toggle mode, repeated presses, final syllables, and clipboard restoration.
- Hold beyond two minutes and up to five minutes. Verify a visible warning and
  duration stop; release the key before insertion and confirm no automatic restart.
- Simulate recognition slowdown and worker exit. Confirm capture remains controllable,
  errors stay visible, incomplete audio is not pasted, and retry/cancel work.
- Change foreground windows during speech. The transcript must be offered for Copy.
- Verify task editing, 90-minute timers, Pomodoro, repeating alarms, snooze, contest
  connection errors, offline cached schedules, and reminder focus preservation.
- Check 100%, 125%, 150%, and 200% Windows display scaling; keyboard focus must reach
  every control. In long settings forms, scroll to Save and use keyboard navigation.
- Install over an earlier version. Preserve settings, dictionary, history, SQLite
  tasks/timers, credentials, and cached models. Check migration backups.
- Uninstall while the tray app and speech model are running. Remove the executable,
  its workers, shortcuts and startup registration, preserve user data,
  then reinstall and confirm recovery.

Automated replay and offscreen UI tests complement these checks; they do not prove
physical microphone/keyboard behavior or compatibility with every destination app.

## Publishing

Target repository: https://github.com/MD-SOHAIL-AI/voiceprompt

CI tests pull requests and main, builds an explicitly unsigned test installer,
and uploads artifacts labelled `VoicePrompt-windows-x64-unsigned-preview`.
It does not create or publish releases. Review native bridge, frozen worker,
installer and manual acceptance evidence, signing status, notices and release
notes before a separately authorized publication. Main-branch pushes do not
publish a release.

For a local build, create a draft release using the checked artifact and checksum:

```powershell
gh release create v0.6.0-preview.1 release/VoicePrompt-Setup-0.6.0-x64-unsigned-preview.exe release/VoicePrompt-Setup-0.6.0-x64-unsigned-preview.exe.sha256 release/VoicePrompt-Setup-0.6.0-x64-unsigned-preview.exe.signing.json --repo MD-SOHAIL-AI/voiceprompt --draft --prerelease --title "VoicePrompt 0.6.0 unsigned Windows preview" --notes-file docs/release-notes-0.6.0.md
```

Users download from the repository's Releases page. The in-app update action opens
the full release list so both published previews and stable builds are discoverable.
An update uses the same installer and leaves user data in place.
