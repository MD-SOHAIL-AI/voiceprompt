# VoicePrompt 0.7.1 RC 1 acceptance

Date: 6 November 2026. Stable publication remains held for device acceptance.
This record separates code fixes from verified runtime behavior. CI artifacts
are tied to their source commit and retained for 90 days. Local reports live in
ignored `build/`; they contain counts and metrics, not personal speech or audio.

| Gap | Engineering result | Acceptance |
|---|---|---|
| R1: shared cache deletion | Repository-scoped deletion with containment checks; duplicate revisions across repositories, shared blobs, other refs, locked files and invalid plans covered. Nested-file discovery fixed. | Model library suite passes locally. |
| R2: unequal release checks | Shared source/clipboard/browser/model/audit gates used by main and stable workflows; Rust auditing in both native jobs. | Local checks and exact-source CI required. |
| R3: unverified hosted assets | Stable and preview drafts are independently downloaded before promotion. Stable metadata is verified by the packaged native verifier. | Tamper, missing asset, wrong version/channel and invalid-signature tests pass. |
| R4: repeated 0.7.0 identity | All version sources identify 0.7.1-rc.1; eventual stable 0.7.1 is newer than existing 0.7.0 builds and this candidate. | Metadata synchronizer and semver regression. |
| R5: catalog service | Signed metadata publication now verifies native trust and hosted bytes, rejects rollback/reused versions, and restores previous metadata on upload failure. | Native verification and live commissioning pending candidate build. |
| R6: onboarding | Download/select/prepare instructions agree with the backend; missing models disable Prepare; dismissed setup reopens. | Browser lifecycle checks pass. |
| R7: device acceptance | Previous-stable schema migration, backup and history preservation added to source/frozen bridge checks. CI tests authenticated 0.6.3 installation, candidate upgrade, binary rollback, restoration and uninstall. | Physical speech, app matrix and clean Windows 10/11 accounts remain unverified. Binary rollback is not certification that older engines understand newer data. |
| R8: publisher identity | Existing update-signing identity preserved. | Publisher signing/SmartScreen deferred by owner. |
| R9: preparation | Candidate notes, version tool and current usage docs added; evidence retained for 90 days. Verifier license added to preview packages too. | Package build and artifact audit pending. |
| R10: controls | Stable publication split into a production environment job. | Remote branch/tag/environment settings must be verified separately. |

## Local verification

- Python, frontend, model library and publication regressions pass; final counts
  and CI links will be recorded after the complete candidate verification.
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

## Before broad stable distribution

Record physical microphone/hotkey trials and paste behavior in Notepad, Edge and
VS Code, including rapid taps, final syllables, focus changes and clipboard changes.
Record normal-user clean Windows 10 and Windows 11 installation/upgrade/uninstall,
data recovery with a backup, screen-reader checks and display scaling. Attach OS
build, artifact SHA-256, date and result. Unknown results stay unknown. Publisher
signing is the explicit deferred exception and must remain disclosed.
