# Desktop preview validation

Validated locally on 17 October 2026 using Windows x64 and Python 3.10.6.

## Automated checks

146 unit and UI regression tests passed locally. Coverage includes independent capture
stop during decoder stalls, retained audio, five-minute duration policy, recovery
timeouts, injected/repeated hotkeys, process termination, clipboard input layout,
configuration backups, neutral defaults, Qt navigation, settings, tasks, timers,
history, and the existing planner/recognizer regressions.

The Qt pages also fit the minimum 800 × 560 window without horizontal page
scrolling. CI excludes the twelve retired Tk reference-screen tests using
`VOICEPROMPT_TEST_LEGACY_TK=0`; these remain enabled by default for local reference
checks. The shipped interface's Qt and service tests remain mandatory in CI.

Qt renders of all seven pages and onboarding were inspected at 100% and 150%.
The offscreen renderer initially lacked Windows font enumeration; it now loads
installed Segoe UI for previews without bundling Microsoft's font files.

The frozen self-check successfully initialized Qt, launched all four recognizer
workers, and loaded the bundled RNNoise native library without model downloads,
keyboard hooks, microphone access, or personal settings access.

## Five-minute endurance replay

The final run replayed the licensed public speech asset repeatedly at microphone
pace through the real Nemotron CPU worker, with noise suppression and cloud
cleanup disabled. It completed 300 seconds and returned final text.

| Measurement | Result |
| --- | ---: |
| Audio replay | 300.0 seconds |
| Total session wall time | 301.05 seconds |
| Release to final text | 1.03 seconds |
| Peak recognition queue | 1.94 seconds |
| Buffer overflow | No |
| Parent peak working set | 78.2 MiB |
| Model worker peak working set | 1000.7 MiB |

The model worker is launched with the base interpreter and the project's module
paths when running from source. This avoids monitoring only Windows' venv
redirector and ensures cancellation terminates the actual model process.

This is an endurance/throughput check, not an accuracy benchmark. It does not
measure physical keyboard events, microphone capture, destination rendering,
or actual paste latency. The parent memory includes the replay harness and is
not a measured Qt application's total working set.

## Remaining stable-release acceptance

Native Computer Use automation could not connect in this session. Physical-key
and microphone checks, destination-app paste, screen readers, full Windows
scaling coverage, and clean Windows 10/11 VM acceptance remain on the release
checklist. The preview has no supplied code-signing identity and is unsigned.

The local installer check passed installation, reinstallation, all four workers,
uninstallation, and preservation of the pre-existing startup registration.
Release scripts record these results under build/ and CI retains them as artifacts.
The local installer check
does not substitute for the clean-machine and physical-device checks above.
