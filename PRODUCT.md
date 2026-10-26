# VoicePrompt

<!-- impeccable:product-schema 1 -->

## Platform

Windows desktop, implemented with Python and PySide6/Qt Widgets. This is a native utility,
not a website or a mobile application.

## Users and purpose

The user dictates text into other applications and manages study and daily activities,
including DSA learning, exercise, and programming contests.

## Confirmed workflows

- Hold Right Ctrl to dictate, release to finish, and paste into the foreground app.
- Support five-minute recordings with visible stop reasons and in-memory recognition retry.
- First-run microphone setup, local model downloads, history, and a per-user Windows installer.
- Manage local tasks, arbitrary-duration activity timers, Pomodoro cycles, and alarms.
- Receive gentle recording and reminder sounds without losing keyboard focus.
- Follow Codeforces, LeetCode, CodeChef, and AtCoder contest schedules.
- Keep reminders available through the Windows tray and recover state after restart.

## Constraints

- Local speech recognition and offline planner storage remain functional.
- Contest refreshes run separately from dictation; CLIST uses the user's own key.
- Preserve existing tasks, settings, and timer behavior throughout visual changes.
- The redesign must address blurry text and make the complete interface easier to use.
- The user normally opens the Planner briefly to manage tasks and timers. Fast
  entry and starting a session should be easy to find without scanning settings.
