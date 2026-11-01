# VoicePrompt stable release acceptance

A passing GitHub Actions check means the automated suite, frozen worker smoke tests,
installer compilation, live-uninstall checks, and packaging checks have passed on
a CI Windows runner. It **does not** establish safe operation on user hardware.

For the update-signed distribution channel, follow [app updates](app-updates.md)
and the mandatory checks in `release.yml`. Update authentication uses the
existing app signing identity and does not claim Windows publisher certification.
The checklist below records the broader hardware and publisher-signing
acceptance work; publishing an update does not establish those manual results.

## Full hardware and publisher-signing acceptance

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

`windows.yml` publishes an unsigned beta only after an explicitly marked merge
and passing checks. `release.yml` publishes update-signed stable packages after
its signature, native, and installer gates. The complete hardware/publisher
certification checklist above remains separate and must not be represented as
completed by CI. Installed versions 0.6.1 and later can check for, download, and
verify stable updates; installation starts when the user chooses Restart to
update. Earlier versions open GitHub Releases and need a manual upgrade once.

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
`vMAJOR.MINOR.PATCH-preview.N` or `vMAJOR.MINOR.PATCH-beta.N`. Stable-channel
tags use `vMAJOR.MINOR.PATCH` and the update-signed release workflow. Release
notes must distinguish automated verification from outstanding manual checks.
