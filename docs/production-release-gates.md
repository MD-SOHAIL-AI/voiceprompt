# VoicePrompt stable release acceptance

A passing GitHub Actions check means the automated suite, frozen worker smoke tests,
installer compilation, live-uninstall checks, and packaging checks have passed on
a CI Windows runner. It **does not** establish safe operation on user hardware.

## Release blockers (all required for a stable release)

- [ ] The proposed release commit has green Windows Actions and a checksum-matched installer.
- [ ] A clean Windows 10 x64 normal-user VM installs, launches, upgrades from 0.4.0,
      uninstalls while running, and preserves user data and portable instances.
- [ ] A clean Windows 11 x64 normal-user VM performs the same full lifecycle.
- [ ] An actual microphone is selected; starting, stopping and rapid hotkey
      presses work; the last spoken syllables are captured.
- [ ] A five-minute held recording, aborted recording, audio device removal,
      ASR worker crash and queued replay behave correctly without truncated pastes.
- [ ] Paste into Notepad, browsers, IDEs and other normal-elevation applications.
      With a destination changing focus, only the explicit Copy option is offered.
- [ ] Clipboard changes made by the user during dictation are never clobbered,
      and failed paste restores the previous text when safe.
- [ ] CPU-only offline cached model operation and an interrupted first download
      are tested without network access or access to test-user secrets.
- [ ] Settings, history, tasks, alarms and contest credentials survive updates,
      failed updates, a reboot and uninstall; no telemetry is sent without consent.
- [ ] User-input accessibility, screen reader, keyboard-only controls and DPI
      scaling at 100%, 125%, 150% and 200% are tested on real Windows displays.
- [ ] All distributed dependencies, native binaries and model license conditions
      are reviewed; bundled notices are present and dependency vulnerabilities
      are evaluated.
- [ ] The EXE and installer are Authenticode signed with an authorized, trusted
      publisher identity, timestamped, and signatures are verified after packaging.
      The speech engine and embedded uninstaller have the same signing identity.
      Attach the final `.signing.json` audit and verify installed executable
      signatures with `check_installer.ps1` on a clean account.
- [ ] A rollback installer and customer recovery instructions are available.
- [ ] The final SHA-256 checksum is independently verified on the exact published
      EXE bytes and GitHub release assets are checked after upload.
- [ ] Release notes accurately explain Windows support, voice-data privacy,
      local-only AI processing, signing status, and manual-update instructions.

Record test device/OS build, result, reproduction evidence, reviewer, date and
artifact SHA-256 in a release-specific acceptance record. Do not place customer
transcripts, API keys, or personal data in acceptance artifacts.

**Policy:** The `windows.yml` tag job may create or repair **draft previews**.
Stable publication requires the separately reviewed gates above and must not
be described as automatic deployment to installed applications. The current
Check for updates action opens GitHub Releases; it does not silently install.

## CI coverage vs manual coverage

CI: Windows Python tests, typed/bytecode checks, all speech-worker imports,
RNNoise native library, installer build, installation/reinstallation, two live
uninstall startup variants, related startup cleanup, portable copy isolation,
and saved-data preservation.

Manual: microphone/hotkey/audio driver interoperability, target application
paste, focus conflicts, screen readers, full display/DPI verification, actual
model accuracy, independent legal/security review and publisher signing.

## Versioning

Do not retag or overwrite published releases. Preview identifiers use
`vMAJOR.MINOR.PATCH-preview.N`. Stable tags use `vMAJOR.MINOR.PATCH` only
after the evidence above is attached to the approved release.
