# VoicePrompt 0.6.3

Delivers the floating island fix through VoicePrompt's signed in-app update
channel. Installed apps on 0.6.1 or 0.6.2 can discover this newer version.

## Update your app

Open **Settings → Check for updates**, choose **Update now**, then select
**Restart to update** when your work is saved. Automatic checks also announce
the update while enabled. Updates wait for recording, recognition, pending
paste, retained-audio recovery, and unsaved forms to be resolved.

Settings, history, dictionary entries, tasks, timers, alarms, startup choices,
and cached speech models are preserved. The app reopens after installation.

Versions older than 0.6.1 need one manual installation of
**VoicePrompt-Setup-0.6.3-x64.exe** from this release. Later releases can then
use the in-app update flow.

## Included fixes

- Remove the unwanted native title bar and minimize/close controls behind the
  floating island, including after hiding, showing, expanding, or collapsing it.
- Use the Windows no-redirection-bitmap transparency path for the island.
- Preserve the island's own controls and the main window's normal controls.
- Include the existing local dictation, recording recovery, planner, appearance,
  and updater improvements from the recent beta releases.

The application behavior matches 0.6.2 Beta 1 apart from release versioning;
this release adds stable-channel delivery and authenticated update metadata.

## Update authenticity and validation

The attached `latest.json` is signed with the existing update identity already
trusted by updater-enabled installations. The app verifies that signature and
the installer's exact size and SHA-256 before installation.

The release workflow checks Python/frontend/Rust regressions, the update UI,
frozen speech workers, native windows and appearance, installer lifecycle, and
native update-signature verification before publishing the release as latest.
The preceding beta also passed the Windows regression, dependency-audit,
native-window, installation/reinstallation, and live-uninstall checks.

Cryptographic update signing is separate from Windows publisher signing. These
Windows binaries are not Authenticode signed; manual downloads may show a
publisher or SmartScreen warning. Physical microphone, keyboard, screen-reader,
Windows 10/11 hardware, and full display-scaling acceptance remain manual checks.

Speech recognition and transcript processing remain local. Model downloads,
optional contest services, and app update checks retain their existing network
behavior. Application code remains MIT licensed; dependency notices are bundled.
