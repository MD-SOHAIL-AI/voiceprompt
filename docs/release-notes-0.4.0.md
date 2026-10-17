# VoicePrompt 0.4.0 preview

- A new Qt desktop with dictation, history, tasks, focus timers, alarms, contests,
  settings, and guided microphone setup.
- Five-minute recordings, visible stop reasons, processing backlog feedback,
  and in-memory retry after recognition failure.
- Capture stops independently of a slow decoder. All speech engines run in a
  separate process; final text is inserted once, after modifiers are released.
- A per-user Windows installer with no Python installation required.
- Existing preferences and planner data are preserved, with migration backups.

Download the x64 Setup executable, install, and follow the setup steps. Model
weights download separately on first preparation; subsequent dictation works
offline. Optional cloud cleanup is off by default.

This preview is unsigned unless its release explicitly identifies the verified
publisher. Code-signing credentials are not included in the project. Installer
and clean-machine acceptance checks must be reviewed before promoting a preview
to a stable release. Windows 10/11 x64 is the first target; other platforms are
not packaged in this release.
