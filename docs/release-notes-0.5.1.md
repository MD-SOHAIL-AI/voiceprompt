# VoicePrompt 0.5.1 — unsigned Windows preview

Download **VoicePrompt-Setup-0.5.1-x64.exe** from this release for Windows 10/11 x64.
Run Setup to install or upgrade. Python and Node.js are not required on the user's
computer. The installer preserves settings, history, tasks, credentials and cached
models when upgrading an existing installation.

This is an **unsigned preview**. The installer is not code-signed, and Windows may
display an unknown-publisher or reputation warning. Physical microphone quality,
global keyboard hardware, screen readers, sleep/wake and the full display-scaling
matrix still need manual acceptance; this release does not certify those checks.

## What's new

- A TypeScript desktop with Dictation, History, Tasks, Focus timer, Alarms,
  Contests and Settings.
- A compact floating island with a live microphone waveform, timer and alarm
  countdowns, contest reminders and snooze controls.
- Neutral Black as the default theme, plus Forest, Graphite, Ocean, Lavender and
  Sand. All six palettes offer light and dark variants; System brightness follows
  Windows.
- Saved **Show floating island**, **Keep island visible** and **Island transparency**
  controls in Settings → Appearance. The expanded island also has a pin button.
  Transparency ranges from Solid to 25%; text and controls remain opaque.
- Appearance changes update both windows without reloading the speech model.

## Fixes

- Preserve the actual engine startup failure instead of replacing it with a
  generic stopped message. If an older tray instance blocks startup, quit that
  instance and select **Restart engine**.
- Reconnect the interface after engine restart and retain planner state.
- Keep the compact island from taking foreground or keyboard focus.
- Accept native date/time input values when saving tasks and alarms.
- Preserve disabled alarms while editing, guard stale timer/reminder actions,
  and bound reminder replay and sound delivery.
- Keep optional planner failures separate from voice typing, and offer Copy
  when the original paste destination is no longer safe.

## Installation and model downloads

Setup includes the official Microsoft WebView2 bootstrapper and installs the
runtime only when missing. That first runtime installation needs internet access.
Speech model weights download separately when prepared; cached models remain
available offline. CLIST contest access and optional text cleanup use the user's
own credentials.

## Verification

The attached installer is the exact artifact from the passing
[Windows build](https://github.com/MD-SOHAIL-AI/voiceprompt/actions/runs/40433974431).
Its SHA-256 checksum is attached alongside it. Build metadata identifies both the
tested artifact commit and release-tag commit; subsequent source changes are
limited to ignore rules and release documentation.

Checks passed for the native main window and island, all twelve theme variants,
text/control contrast, serious/critical accessibility rules, preference persistence,
transparency, pin/hide behavior, duplicate-instance recovery, engine restart, frozen
speech workers and RNNoise, and installer install/reinstall/live-uninstall with
saved-data preservation. The installed package also passed the native workflow
checks locally using an isolated profile.

The four frozen speech workers are Whisper, Moonshine, Parakeet and Nemotron.
Worker smoke checks do not measure recognition accuracy or physical microphone
performance.

Bundled licenses and third-party notices are included in the installer. This
release does not change the project's MIT license.
