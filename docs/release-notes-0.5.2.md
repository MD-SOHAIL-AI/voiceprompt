# VoicePrompt 0.5.2 dictation repair

The recording pipeline could finalize after an empty queue read even when the
microphone had just delivered more audio. It now checks that capture has ended
and the queue is empty before finalizing. A regression test reproduces the lost
audio in the previous code and verifies all samples reach recognition.

Microphone capture now starts before native recognition stream setup, keeping
initial speech while that setup completes. The managed speech worker sends
100 ms audio blocks instead of making a synchronous pipe call for each small
microphone callback, and flushes the final remainder exactly once.

Held recording keys or modifiers no longer leave the controller waiting
indefinitely to paste. After two seconds, the result is available to copy and
the controller becomes available again. Empty recognition results keep audio
in memory for retry. Cancel clears model readiness because interrupting the
worker unloads it.

Diagnostics add recording duration, decoded audio duration, backlog at capture
stop, and modifier wait time. They contain no transcript text or audio.

## Validation and local package

The Python suite runs 168 tests with two optional tests skipped and no failures. Source
and frozen engine bridge checks pass. The frontend production build and its
10 tests pass. The packaged desktop smoke check verifies version 0.5.2,
all four speech workers, and RNNoise.

The rebuilt native app passes the full WebView2 UI checks, including the
Settings version label, all seven screens, twelve theme variants, planner
actions, reminders, engine restart, and main-window/island synchronization.

Five licensed public Indian English clips (63.12 seconds, 183 reference words)
were replayed through the managed Nemotron CPU worker with noise suppression
off and on. All ten replays returned text without queue overflow, and decoded
audio duration included each clip plus its 180 ms release tail. Median
release-to-final time was 1.04 seconds without suppression and 1.12 seconds
with it; word errors were 15/183 and 14/183 respectively. This small sample
does not establish accuracy for the user's voice.

One replay while build tools were running took 23.50 seconds to finalize.
This repair removes lost-audio paths and unnecessary worker calls; it does
not eliminate delays from CPU or memory pressure. A second simultaneous
Nemotron instance failed native memory allocation on this laptop. The
single-model check closed the installed app normally for replay, then reopened
it. These timing results are not a controlled before/after speed comparison.

The Settings version label now imports the desktop package version, so each
release updates the label without editing screen text. Build checks reject
inconsistent engine, desktop, and frontend versions, including an explicitly
supplied older shell. Native UI verification compares the displayed Settings
version with the release metadata.

The final local update packages the rebuilt 0.5.2 engine with the 0.5.2 desktop
shell. Project-local Microsoft compiler/SDK components and Rust's bundled
linker allow the desktop rebuild without a system Visual Studio installation.
The staged `build-manifest.json` records the engine version, desktop version,
and desktop executable hash.

To reproduce an engine repair with an explicitly selected existing shell:

```powershell
.\scripts\build_desktop.ps1 -NativeExecutable dist\VoicePrompt\VoicePrompt.exe -AllowUnsignedPreview
```

Only supply a shell matching the current frontend and native source and the
release version; an older shell is rejected. The default build compiles the
desktop shell normally.

`scripts/verify_dictation_reliability.py` replays existing WAV files through the
production speech worker at microphone pace, optionally comparing noise
suppression. It uses cached models offline and reports timing, sample coverage,
and optional reference word errors without storing transcripts. The default
input is bundled licensed public speech. `scripts/verify_single_model.ps1`
can temporarily close and reopen an installed VoicePrompt for the check when
Windows cannot allocate two speech models at once.

Replay does not verify physical microphone capture, global-key handling, or
delivery into another application's editor. Those still require a local
dictation check. This is a local repair package, not a published stable release.
