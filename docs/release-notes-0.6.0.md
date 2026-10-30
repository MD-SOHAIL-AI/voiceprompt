# VoicePrompt 0.6.0 local-only release candidate

This update keeps AI processing on the device and repairs recording recovery,
storage failures, desktop transport, and clipboard handling. It is a release
candidate; stable publication still requires the production acceptance record.

## Changes

- Removed Gemini and OpenRouter processing, API-key forms, environment-key
  loading, and the Gemini SDK. Upgrade retires only VoicePrompt's old cloud
  credentials. Model downloads and contest services remain available.
- Added configuration version 7 with migration backups and explicit recovery
  controls for unreadable settings. Existing model and microphone choices stay.
- Diagnostic and history write failures no longer leave dictation busy or block
  completed text. Empty retries keep audio, and recovery is visible in both windows.
- Failed automatic paste leaves the transcript available to Copy. Native clipboard
  snapshots preserve supported formats, and sequence checks respect subsequent
  user changes. Unsupported or oversized clipboard formats fall back to Copy.
- Added original soft start/release clicks and idle-only preview buttons.
- Smoothed the floating timer ring, softened the compact border, and added brief
  panel transitions without changing its native footprint. Reduced-motion
  preferences and steady countdown spacing are preserved.
- Bounded planner and history messages by encoded size; full notes/transcripts
  load separately. Alarm pages share stable ordering. Oversized events no longer
  quit the speech engine.
- Queued settings merge against the latest desired state. Desktop events carry
  an engine generation, and stale replies cannot replace a restarted engine.
- Added recording-stage timings, processing ratio, finalization progress, memory
  measurements, and a shared finalization deadline. Diagnostics contain no audio
  or transcript text.
- Added opt-in Whisper phrase decoding and whole-recording comparison tools.
  It remains off by default because its measured tail latency did not meet the
  activation gate. Existing Whisper behavior is preserved.

## Validation and launch status

The scenario register and current measurements are in
[production hardening](production-hardening-0.6.0.md). Replay uses licensed public
speech and measures recognition, not physical microphones or destination-app
rendering. A full Windows hardware/VM matrix and trusted publisher signing remain
mandatory. The Check for updates action opens Releases; updates use the installer.

Retry audio stays in memory and is cleared on exit. Upgrading preserves planner
data, cached models, dictionary, and history. A schema-6 backup is retained for
recovery; older binaries cannot directly read schema-7 settings. Keep a validated
0.6.x installer as the compatible rollback candidate.
