# VoicePrompt 0.6.2 Beta 1

Fixes the unwanted Windows title bar and minimize/close buttons showing through
the floating island's transparent background.

## Download and install

Download **VoicePrompt-Setup-0.6.2-x64-unsigned-preview.exe** from this release.
Finish any recording, save your changes, and quit VoicePrompt from the system
tray before installing. Install over your existing copy. Settings, history,
tasks, timers, alarms, and cached speech models are preserved.

The app displays **0.6.2**. Python and API keys are not required.

## Changes

- Remove native caption, minimize/maximize, close, and resizing-frame styles
  from the floating island, including after expanding and collapsing it.
- Use the Windows no-redirection-bitmap transparency path for the island.
- Keep the island's own collapse control and the main window controls available.
- Check the real native window styles during appearance, expansion, collapse,
  and hide/show verification.
- Synchronize Windows executable version metadata with the application version.

This release also includes the previous beta's local dictation, recording
recovery, planner, appearance, and in-app update features.

## Release channel and verification

This is an unsigned Windows 10/11 x64 beta. Windows may show publisher or
SmartScreen warnings. Download this beta manually from GitHub Releases; beta
versions are excluded from the stable in-app update feed.

The publication workflow requires Python/frontend/Rust checks, dependency audits,
frozen-engine checks, native island and appearance checks, and installer
install/reinstall/live-uninstall checks. It verifies the uploaded installer's
SHA-256 before publishing. Checks run on a Windows GitHub Actions runner;
physical microphone, keyboard, display-scaling, and Windows 10/11 hardware
acceptance remain separate manual checks.

Speech recognition and transcript processing remain local. Model downloads,
optional contest services, and app update checks retain their existing network
behavior. Application code remains MIT licensed; dependency notices are bundled.
