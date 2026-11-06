# VoicePrompt 0.7.1 RC 1 acceptance

Date: 6 November 2026. Stable publication remains held for device acceptance.
Candidate source: `6059ce2c9979f3224cb14ae4d99d83672499562e`.
The later documentation commit does not change the packaged application.
This record separates code fixes from verified runtime behavior. CI artifacts
are tied to their source commit and retained for 90 days. Local reports live in
ignored `build/`; they contain counts and metrics, not personal speech or audio.

| Gap | Engineering result | Acceptance |
|---|---|---|
| R1: shared cache deletion | Repository-scoped deletion with containment checks; duplicate revisions across repositories, shared blobs, other refs, locked files and invalid plans covered. Nested-file discovery fixed. | Model library suite passes locally. |
| R2: unequal release checks | Shared source/clipboard/browser/model/audit gates used by main and stable workflows; Rust auditing in both native jobs. | Exact-candidate Windows CI passed. |
| R3: unverified hosted assets | Stable and preview drafts are independently downloaded before promotion. Stable metadata is verified by the packaged native verifier. | Tamper, missing asset, wrong version/channel and invalid-signature tests pass. |
| R4: repeated 0.7.0 identity | All version sources identify 0.7.1-rc.1; eventual stable 0.7.1 is newer than existing 0.7.0 builds and this candidate. | Metadata synchronizer and semver regression. |
| R5: catalog service | Signed metadata publication verifies native trust and hosted bytes, rejects rollback/reused versions, and restores previous metadata on upload failure. | Version 1 is live: eight reviewed models; public HTTP download and native signature verification passed. |
| R6: onboarding | Download/select/prepare instructions agree with the backend; missing models disable Prepare; dismissed setup reopens. | Browser lifecycle checks pass. |
| R7: device acceptance | Previous-stable schema migration, backup and history preservation added to source/frozen bridge checks. CI tests authenticated 0.6.3 installation, candidate upgrade, binary rollback, restoration and uninstall. | Physical speech, app matrix and clean Windows 10/11 accounts remain unverified. Binary rollback is not certification that older engines understand newer data. |
| R8: publisher identity | Existing update-signing identity preserved. | Publisher signing/SmartScreen deferred by owner. |
| R9: preparation | Candidate notes, version tool and current usage docs added; evidence retained for 90 days. Verifier and native dependency licenses added to preview packages too. | Final package built, installed, audited and independently downloaded from its GitHub draft. |
| R10: controls | Stable publication split into a production environment job. | Main requires both CI jobs for non-admin changes; force push/deletion disabled. Version tags cannot be moved/deleted. Production and catalog environments require owner review and restrict refs. The sole repository administrator retains the main-branch bypass. |

## Local verification

- [The complete candidate CI passed](https://github.com/MD-SOHAIL-AI/voiceprompt/actions/runs/42187284791),
  including the source guard and native notice collection. The application has
  14 frontend and 14 Rust tests; the model library has 22 regression tests.
  Python test totals vary with legacy UI availability; consult the CI log for
  its complete count and explicit skips. Local tests passed, including the new
  source and notice guards.
- [Windows CI for the application fixes passed](https://github.com/MD-SOHAIL-AI/voiceprompt/actions/runs/42184185958)
  at `4fe2bbc3ff7922e95f723bbbcd0961fce7e15c80`, including real clipboard,
  browser/model flows, dependency audits, native checks, upgrade from 0.6.3,
  binary rollback/restoration and live uninstall. The final packaging guard is
  verified separately on its subsequent commit.
- Model lifecycle browser checks cover empty-cache setup, downloading, cancelling,
  selection, selected-model deletion, recovery, narrow layout and serious/critical
  automated accessibility checks.
- A five-minute CPU Nemotron replay submitted and processed all 4,802,880 samples
  (300.18 seconds including the release tail), with no overflow. Finalization
  took 1.90 seconds and worker peak memory was approximately 1,006 MB. The report
  binds the Python-source hash and fixture hash. This is public WAV replay, not
  physical microphone, clipboard, or accuracy certification.
- On this automation token, creating a private window station for the clipboard
  test was refused. The script stopped before accessing the user's clipboard.
  The clean hosted runner runs the explicitly restricted fallback; previous
  baseline private-station results do not count as a new candidate pass.
- A real Windows 11 Notepad destination received the complete synthetic
  105-character sentence once, including its final sentence. Destination
  consumption and automatic clipboard restoration both passed. The text and
  character count were checked visually because Notepad's accessibility provider
  returned stale text. This checks the injection path, not physical speech.
- A second five-minute Nemotron CPU replay with RNNoise enabled processed all
  4,802,880 samples, with no overflow; finalization took 1.22 seconds and worker
  peak memory was approximately 963 MB. Its source commit is the fixes commit
  linked above. No transcript text or audio is stored in the report.
- The new package guard compares all 37 embedded application modules with the
  checkout. It rejected the stale local model-library bytecode and has regression
  coverage for stale nested functions, different build paths and unknown modules.
- Packaging now cleans PyInstaller's cache, then checks the resulting bytecode.
  The repaired local engine passed all 37 module comparisons. Native notices
  are collected for all 251 packages in the locked Windows dependency graph,
  including build dependencies. Six missing notice sets use reviewed upstream
  copies; unmodified MPL source files and pinned source URLs are included.
  Future dependencies without notices block packaging.
- Python and npm audits report no known vulnerabilities; the Rust audit reports
  zero vulnerabilities. Its unmaintained/build-time and non-Windows warnings
  remain visible in the report. `glib`, `zvariant` and the yanked `async-executor`
  are absent from the Windows target graph; no framework-wide upgrade was made
  solely to silence those warnings.

## Candidate package and local upgrade

`VoicePrompt-Setup-0.7.1-rc.1-x64-unsigned-preview.exe` has SHA-256
`44a5d0e3ffc9e1ad084e96a939edecec3f4cf3ad7eb38879b9ba388a0c95cee9`.
The source guard verified all 37 embedded Python modules. The installed engine
and native shell match the verified stage. The native shell reports production
mode, embedded frontend, version 0.7.1-rc.1 and no debug mode.

The local upgrade preserved all 17 backed-up settings/data files byte-for-byte;
model weights were kept in place. VoicePrompt was left closed. Backup details
are kept locally in ignored `build/candidate-data-backup.json` and are not uploaded.

The [GitHub candidate draft](https://github.com/MD-SOHAIL-AI/voiceprompt/releases/tag/untagged-5acb7e6c581014655b6e)
contains the installer, checksum and honest unsigned audit. The three assets
were downloaded independently and matched exactly. The final machine-readable
acceptance report is attached to that draft. The stable update feed remains on
0.6.3. No stable 0.7 release was published.

## Before broad stable distribution

Record physical microphone/hotkey trials and paste behavior in Notepad, Edge and
VS Code, including rapid taps, final syllables, focus changes and clipboard changes.
Record normal-user clean Windows 10 and Windows 11 installation/upgrade/uninstall,
data recovery with a backup, screen-reader checks and display scaling. Attach OS
build, artifact SHA-256, date and result. Unknown results stay unknown. Publisher
signing is the explicit deferred exception and must remain disclosed.
