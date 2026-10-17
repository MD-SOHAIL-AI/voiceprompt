# Build and release VoicePrompt

## Validated target

Windows x64, Python 3.10, PySide6 Essentials 6.10.3, PyInstaller 6.22.3, Inno Setup 6.
The source lock file records the tested environment, including optional RNNoise.
Build on Windows; do not copy a Python virtual environment to users.

## Local release

1. Install `requirements-lock.txt` into a dedicated virtual environment.
2. Run `python -m unittest discover -s tests -v` from that environment.
3. Run `scripts/build_windows.ps1`, supplying `-Python` and `-InnoCompiler` as needed.
4. Inspect `build/frozen-smoke.json`. Every selected backend must describe itself;
   the release also includes the optional RNNoise native library.
5. The installer and its `.sha256` file appear under `release/`.
6. Run `scripts/check_installer.ps1` in a clean Windows account. It installs and
   reinstalls with startup enabled and disabled, then uninstalls with a live
   frozen app and speech worker. It checks normal shutdown, all installed files,
   shortcuts, Windows registration, runtime and legacy startup cleanup, unrelated
   startup preservation, and a saved-data marker. Original startup values are
   restored after the test. Evidence is in `build/installer-check.json` and logs.

The folder bundle remains under `dist/VoicePrompt`. It includes the interpreter,
native dependencies, Qt plugins, notices, and assets; model weights remain separate.

## Signing

Supply `-SignThumbprint <certificate thumbprint>` and have Windows SDK `signtool`
available on PATH. The build signs the application before installer compilation,
then signs the installer and timestamps both signatures. Signing failures stop
the build. Keep certificates, PFX files, and private keys outside the repository.
The script never generates a publisher identity or claims an unsigned build is signed.

Code signing can require a paid certificate or a signing service. Without a supplied
identity, publish only an explicitly labelled unsigned preview, following the checks
below. Do not promise that signing removes every Windows reputation prompt.

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

CI tests pull requests and main, builds the installer, and uploads artifacts.
A `v*` tag creates a **draft prerelease** with installer assets. Review the test
evidence, signing status, notices, and release notes before publishing that draft.
Main-branch pushes alone do not publish a release.

For a local build, create a draft release using the checked artifact and checksum:

```powershell
gh release create v0.4.1-preview.1 release/VoicePrompt-Setup-0.4.1-x64.exe release/VoicePrompt-Setup-0.4.1-x64.exe.sha256 --repo MD-SOHAIL-AI/voiceprompt --draft --prerelease --title "VoicePrompt 0.4.1 preview" --notes-file docs/release-notes-0.4.1.md
```

Users download from the repository's Releases page. The in-app update action opens
the full release list so both published previews and stable builds are discoverable.
An update uses the same installer and leaves user data in place.
