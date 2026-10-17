# VoicePrompt 0.4.1 preview

This unsigned Windows x64 preview fixes uninstalling while VoicePrompt is running.

- Requests normal app shutdown before upgrading or uninstalling, releasing the
  microphone, input hooks, speech worker and native libraries before deleting files.
- Stops orphaned or stuck processes only when their executable path belongs to
  this installation. A running source or portable copy is left alone.
- Removes startup entries enabled in app settings as well as the installer task,
  including the historical `Voice Prompt` and `Prompt Voice` names when their
  commands launch VoicePrompt. Unrelated commands are preserved.
- Keeps settings, history, tasks, dictionary, model caches, and developer source.
- Removes empty library directories inherited from a failed older uninstall;
  custom files are preserved and directory junctions are not followed.
- Adds automated live-uninstall checks with a running app and speech worker,
  installed and runtime startup registration, shortcuts and saved-data preservation.

If 0.4.0 reported a successful uninstall but left a running app or files, install
this version into the same folder and then uninstall again. The new installer
repairs the registration and closes the old installed processes first.
