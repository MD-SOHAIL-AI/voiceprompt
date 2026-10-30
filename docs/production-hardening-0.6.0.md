# VoicePrompt 0.6.0 production hardening

Target: Windows 10/11 x64, local AI processing, unchanged existing model choices.
Model downloads and contest integrations remain online. The current candidate
must not be presented as a signed or production-approved release.

## Scenario register

| ID | Priority | Failure and repair | Verification |
| --- | --- | --- | --- |
| R01 | P0 | Diagnostic write failure kept the controller busy; metrics are optional and completion is unconditional. | Application regression |
| R02 | P0 | History write failure prevented paste; text delivery and history persistence now fail independently. | Application regression |
| R03 | P1 | Empty retry discarded audio and left readiness false; retain audio and validate capture readiness. | Application regression |
| R04 | P1 | Recovery controls depended on an error string; show them whenever failed audio exists. | Frontend state test and native UI acceptance |
| R05 | P1 | Queued settings overwrote prior changes; merge against desired settings, publish applied revisions, submit changed fields. | Application regression |
| R06 | P0 | Valid Unicode notes exceeded the IPC ceiling and stopped the app; bounded summaries and separate item retrieval isolate failures. | Transport regression |
| R07 | P1 | Alarm pages overlapped; use identical ordering and actual page lengths. | Pagination regression |
| R08 | P0 | Cloud-processing paths remained available; remove runtime integrations, keys, SDK and legacy controls. | Migration, credential isolation, source/frozen checks |
| R09 | P1 | Clipboard restoration compared text alone; snapshot supported formats and check native ownership sequence. | Injector regressions; hardware paste acceptance pending |
| R10 | P1 | Stale worker/desktop events could affect replacements; fence connections and engine generations, serialize restarts. | Worker/Rust/frontend tests and native bridge acceptance |
| R11 | P1 | Invalid settings prevented all recovery; retain originals and expose explicit backup/default recovery. | Migration regression and source bridge recovery check |
| R12 | P1 | Disabling history erased old entries; zero now prevents writes. Corrupt history stays intact until explicit recovery. | History regressions |
| R13 | P1 | Invalid task dates could break the scheduler; validate dates before storage. | Planner regression |
| R14 | P1 | Slow recognition lacked stage information; bounded finalization, processing/backlog updates, stage and memory metrics. | Session regressions and local replay |
| R15 | P1 | Recording sounds were unsuitable; original rounded start/release clicks replace the tones. | WAV validation; subjective hardware listening pending |
| R16 | P0 | Audio-thread initialization failure left work busy; supervise submitted futures and keep shutdown cleanup independent. | Application regression |
| R17 | P0 | Frame-drop failure could leave readiness true after worker interruption; invalidate readiness and reopen capture. | Application regression |

Current source verification: 192 Python tests completed successfully (two optional
checks skipped), 13 frontend tests passed, the production frontend built, five
Rust tests passed, and Clippy passed with warnings denied. The source bridge
checks include preserved-data restart and explicit settings recovery. Frozen
package and native WebView verification are recorded separately after building.

## Reproducing verification

Use the pinned release environment and run:

```powershell
$env:VOICEPROMPT_TEST_LEGACY_TK='0'
.\.venv-release\Scripts\python -m unittest discover -s tests
.\.venv-release\Scripts\python scripts/check_engine_bridge.py
. .\scripts\windows_toolchain.ps1
Initialize-VoicePromptToolchain
cargo test --manifest-path desktop/src-tauri/Cargo.toml --locked --lib
cargo clippy --manifest-path desktop/src-tauri/Cargo.toml --locked -- -D warnings
cd desktop
npm ci
npm run test
npm run build
cd ..
.\scripts\verify_local_matrix.ps1 -Endurance
.\scripts\build_desktop.ps1 -Python .venv-release\Scripts\python.exe -AllowUnsignedPreview
.\scripts\check_native.ps1 -Python .venv-release\Scripts\python.exe
```

The local toolchain helper supports the existing project-local Microsoft compiler
and SDK layout. Standard release builders should install Microsoft C++ Build
Tools and the Windows SDK. Dependency lockfiles come from a clean environment.

The replay driver closes the installed application normally to avoid loading two
speech models, then reopens it. Use it while dictation is idle. Its recordings are
the existing licensed public evaluation clips; it does not capture microphone audio.

## Acceptance targets and evidence

Targets for the selected CPU configuration: warm 1–30 second dictation median
finalization at most 1 second and p95 at most 3 seconds; five-minute finalization
p95 at most 5 seconds; defined background-load p95 at most 8 seconds. The absolute
finalization deadline remains 30 seconds with in-memory recovery. Five samples
or one endurance replay cannot establish p95 reliability across hardware.

A model change needs at least 30% lower p95 latency, at most one percentage point
worse clean-speech WER, and no worse noisy-speech WER. The existing Nemotron CPU
selection is retained: the small local comparison gives Moonshine substantially
more word errors despite its lower median latency. No general accuracy gain or
controlled before/after speedup is claimed.

Local replay on 30 October 2026: five licensed public clips, 63.12 seconds,
183 reference words per condition, one model loaded at a time. This is a small
accuracy sample; the maximum below is not a p95 qualification.

| Engine | RNNoise | Median finalization | Maximum | Word errors |
| --- | --- | --- | --- | --- |
| nemotron | Off | 0.85s | 1.38s | 15/183 |
| nemotron | On | 0.82s | 1.34s | 14/183 |
| moonshine | Off | 0.64s | 1.11s | 52/183 |
| moonshine | On | 0.65s | 1.65s | 46/183 |
| parakeet | Off | 1.03s | 2.39s | 26/183 |
| parakeet | On | 0.99s | 1.97s | 20/183 |
| whisper phrases | Off | 2.19s | 3.21s | 26/183 |
| whisper phrases | On | 2.26s | 3.33s | 29/183 |

The 300-second Nemotron CPU replay completed in 301.16 seconds, finalized in
1.15 seconds, decoded all 300.18 seconds including the release tail, and had a
0.84-second peak queue with no overflow. Worker peak working set was 1004.7 MiB.

Whisper whole-recording comparison made 25/183 errors without suppression and
30/183 with it; phrase decoding made 26/183 and 29/183. Median phrase latency was
about 2.2 seconds, but its tail latency did not pass the required improvement
gate. **Whisper phrase decoding is available only by explicit opt-in and remains
off by default.** Existing model selection and ordinary Whisper behavior stay.

Machine-readable replay reports live under `evaluation/hardening-0.6.0/` and
automated test/build reports under `build/`. Both are local artifacts. The final
release record must tie verification to the release commit and installer SHA-256.

Python and npm production dependency audits reported no known vulnerabilities.
RustSec 0.22.2 reported zero vulnerability entries and five informational warnings
(`proc-macro-error`, `zbus_names`, `zvariant`, `zvariant_derive`, and `glib`). Reverse
dependency checks for the Windows x64 target show these packages are not in that
target's dependency graph. They remain visible in the full cross-platform lock
audit; no blanket advisory ignores were added.

## Remaining production gates

- Trusted, timestamped publisher signatures on the desktop, engine, installer,
  and uninstaller; an unsigned test artifact cannot satisfy this gate.
- Fresh Windows 10 and 11 normal-user VM installation, upgrade, live uninstall,
  rollback, and saved-data checks. Installer verification deliberately refuses
  to replace an existing registered installation.
- Physical microphone/hotkey/device-removal checks; Notepad/browser/IDE paste,
  focus conflicts, clipboard formats, elevated-target Copy fallback, speaker and
  Bluetooth sound checks, screen reader and 100–200% DPI acceptance.
- Broader accuracy and defined CPU/memory-pressure qualification; signed pilot
  with at least five testers for 48 hours and 100 completed dictations.
- Dependency/model license review, verified final checksums, published asset
  re-download, and a compatible signed rollback candidate.

See [stable release acceptance](production-release-gates.md) for the complete
existing release policy. No stable release should be published until these
entries have dated evidence rather than inferred success.
