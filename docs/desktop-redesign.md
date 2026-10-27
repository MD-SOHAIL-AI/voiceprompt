# Desktop redesign and repair plan

The approved direction keeps all seven tools and replaces the active Qt
presentation with Tauri 2, React 19 and TypeScript. Forest surfaces, mint actions,
local Encode Sans and a labeled sidebar follow the approved main concept. The
later island concept is authoritative for floating controls.

## Implementation stages

1. Preserve local work and synchronize GitHub main. The previous edits are
   retained in a stash and backup branch; implementation uses a feature PR.
2. Audit controller, recorder, history, planner, credentials and packaging.
   Retain the existing four local recognition engines and five-minute session
   isolation. Replace presentation through a headless adapter.
3. Implement a bounded, versioned stdio bridge and native process containment.
   Both windows use the same engine and SQLite planner. Unexpected engine exit
   rejects pending requests and exposes restart recovery.
4. Replace all seven tools, onboarding, error/retry/cancel states and native tray
   controls. Keep a deliberately labeled sample preview for browser development.
5. Implement the compact island: 112 x 32 DIP, expandable to at most 320 x 400.
   Focus countdown/progress, next-alarm countdown, live microphone amplitude,
   grouped reminder previews, quick timers, alarm controls and actionable contest
   notifications share Focus, Alarms and Notifications tabs.
6. Verify engine regressions, browser workflows/accessibility, frozen workers,
   real native WebView2 integration and install/live uninstall. Review the actual
   design evidence and document the final system. Merge only after required
   checks; do not publish a public release as part of this task.

## Repairs included

- Paste requires a valid original destination and unchanged foreground. App-owned
  windows cannot become dictation targets. Copy remains available when unsafe.
- Recording produces a bounded, smoothed amplitude envelope at 30 Hz; audio is
  never shipped through UI events or consumed by the waveform renderer.
- Timer mutations validate session identity. Reminder actions validate revision,
  preventing stale controls in one window from changing newer state in another.
- Reminder presentation is separate from dismissal. Snooze removes the current
  badge until due. Sound counts and rate limits persist through restart.
- Existing notification migrations avoid replaying old previews or sound bursts.
  Contest advance and start reminders are distinct, deduplicated stages.
- Editing disabled alarms preserves their disabled status. History deletion uses
  stable identifiers for old entries and atomic storage updates.
- Native date/time inputs now accept the HTML separator when saving alarms and
  task reminders. Migration backups explicitly close their SQLite connection,
  preventing Windows from retaining a file lock after restart.
- Optional planner corruption leaves dictation available with an explicit error.
- Native startup points to the desktop executable. Quit and uninstall contain
  and stop the engine process tree, matching installed paths only.
- Verification profiles are empty, isolated directories: no personal credentials,
  `.env`, Windows startup mutation, global hotkey, microphone capture or model
  downloads. Real user settings and storage formats are retained.

## Validation evidence and limits

Machine-readable reports are generated under `build/`, with screenshots under
`.impeccable/review/`. Windows CI uploads these as workflow artifacts. The tests
cover protocol bounds/order, state guards, persistent reminder delivery, alarm
edits, contest stage transitions, audio envelope behavior and history identifiers.
Browser automation checks all seven screens and critical planner actions; native
automation uses the packaged Tauri windows and real Python service.

Passing automation does not prove physical microphone quality, every destination
application, global keyboard hardware behavior, Windows Narrator, sleep/wake,
multi-monitor or 100–200% display scaling. Those manual acceptance checks remain
listed in `docs/releasing.md`. No new speech-accuracy claim is made from smoke
tests. Unsigned artifacts remain unsigned; no publisher identity is generated.

## Development tools

The dependency audit prompted a Python 3.11 build floor: patched filelock 4.2.4
and Pillow 13 require it. Certifi was updated to 2026.10.23. The previous Python
3.10 local environment is preserved; packaged users receive the new interpreter.

The workstation has free Playwright MCP (Edge), shadcn MCP and Context7 MCP
configured in Codex, with read-only initialization/tool checks in
`scripts/check_ui_mcps.py`. These are development tools, not app dependencies.
Impeccable supplies the direction, design review and documentation workflow.
Mobbin required a paid plan and was not used beyond the connection check.
