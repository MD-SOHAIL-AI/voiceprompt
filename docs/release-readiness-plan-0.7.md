# VoicePrompt 0.7 release-readiness plan

Reviewed: 6 November 2026. Baseline: `04682002ea727cfaed05633cb5b406a4775fb6e0`.

## Decision

Hold a broad stable release for the remaining device acceptance. The reproduced
cache-deletion defect and the engineering/publishing gaps below have now been
addressed in 0.7.1-rc.1. The candidate is installed locally, has green Windows CI,
and is available as an unpublished release draft. Automated checks do not replace
physical speech and clean Windows 10/11 acceptance.

Implementation is complete as **0.7.1-rc.1**. The original review
below is retained as the problem statement. Current outcomes are tracked in the
[candidate acceptance record](release-acceptance-0.7.1-rc.1.md). Windows publisher
signing and SmartScreen work are explicitly deferred at the owner's request.

## Evidence already available

- [Latest Windows CI passed](https://github.com/MD-SOHAIL-AI/voiceprompt/actions/runs/42176313770)
  for the exact baseline: Python/frontend/Rust checks, dependency audits, native
  window checks, frozen engine checks, installation and live uninstall.
- The Python suite passes 234 tests. CI skips 12 legacy/environment checks; the
  local environment skips two. These counts describe different environments.
- The real Windows clipboard check passes in a private station: delayed 400 ms
  reads, restoration after consumption, a monitor reading before Ctrl+V, and a
  nine-MB screenshot. This is valuable evidence, but does not exercise every
  destination application's Ctrl+V behavior or a physical microphone.
- The local `-done.exe` installer embeds the frontend and reports production
  mode. Its SHA-256 is
  `04d59ae7ea3de015a1ec276394db9b0cfee4dd7e11407317b64bbdf0864ad018`.
  Its desktop, engine and installer are all `NotSigned` in the signing audit.
- Eight catalog models have offline replay evidence. The replay uses a short
  public speech fixture and checks for nonempty output, not broad accuracy.
- A five-minute Nemotron replay exists from 30 October. It predates these
  clipboard/model-management changes and lacks an exact release-commit binding.
- The latest public stable release is
  [v0.6.3](https://github.com/MD-SOHAIL-AI/voiceprompt/releases/tag/v0.6.3).
  No 0.7 release or model-catalog release was found during this review.

## Confirmed gaps

| ID | Priority | Finding | Required result |
|---|---|---|---|
| R1 | P0: before any beta | Shared Hugging Face deletion scans the whole cache and selects by revision hash alone. A disposable fixture reproduced selection of a different repository when two repositories share a hash. | Deletion is restricted to the selected repository/revision, with regression coverage and a containment check before executing its strategy. |
| R2 | P0: before stable | `release.yml` omits the real clipboard check and the Python/npm/Rust vulnerability audits that main-branch CI runs. The model-library browser lifecycle script is not a gate in either workflow. | Common release-required checks run for the exact release source; an older passing ancestor is not sufficient. |
| R3 | P0: before stable | The stable workflow uploads a draft and immediately publishes it. Unlike beta publication, it does not download hosted assets and independently verify the final bytes. | Verify the hosted installer hash, signed metadata and required assets before promoting the draft or updating the public feed. |
| R4 | P1: release identity | Several different local installers identify themselves as 0.7.0. The updater accepts only strictly newer stable versions. | Pick one immutable candidate and define a version path that upgrades existing local 0.7.0 users. |
| R5 | P1: before claiming catalog updates | The `model-catalog` release endpoint returns 404. The bundled catalog works, but the live refresh service is not commissioned. | Publish and verify a reviewed signed catalog, or explicitly scope the beta to its bundled list. |
| R6 | P1: first-run usability | Onboarding says preparation downloads a model, but `_prepare()` requires previously downloaded, verified files. | First-run instructions and available actions consistently guide download, selection and preparation. |
| R7 | Stable acceptance missing | Real microphone, target-app paste, Windows 10/11 normal-user operation, and release-specific upgrade/rollback results are not recorded. | Complete the device and lifecycle matrix below on the exact candidate. Unknown results are not reported as failures or passes. |
| R8 | Distribution decision | The current preview has no Windows publisher signature. Update signing exists and is a separate mechanism. | Choose an explicitly disclosed unsigned beta/update-signed channel or complete publisher signing; never claim Authenticode trust from an update signature. |
| R9 | Release preparation | The beta workflow requires `docs/release-notes-VERSION-beta.1.md`; the 0.7 beta file is missing. README/release guidance contains older versions and validation wording. CI evidence retention is only one day. | Prepare accurate channel-specific notes and retain evidence with the released version. |
| R10 | Release controls | GitHub reports `main` as unprotected. The stable workflow has no release environment/reviewer gate in its configuration. | Establish and verify the intended branch/tag rules and publication review process. Existing secret and environment settings need confirmation, not assumptions. |

P0 means a release blocker in this plan. P1 means required preparation or
qualification for the advertised release scope; it does not imply every item is
an application defect.

### R1 reproduction and fix design

Relevant code: `voiceprompt/model_library.py`, `ModelLibrary.delete()`, lines
395–397 in the reviewed baseline. It calls
`scan_cache_dir(...).delete_revisions(model['revision'])` across the entire hub.
The dependency assumes revision hashes identify repositories uniquely; forked
or copied repositories can retain the same commit identity.

The dry-run fixture selected `fixture/first`, but the generated strategy selected
`models--fixture--second`. The strategy was **not executed**. The reproduction
and result are in ignored developer artifacts:
`build/readiness-cache-scope.py` and `build/release-readiness-cache-scope.json`.
No real model cache was changed.

Restrict the cache information to the exact repository/type/path before calling
the dependency deletion planner. Verify every planned repository, snapshot,
reference and blob path lies inside that repository before executing. Preserve
other revisions' referenced blobs. Fail closed if the inventory or cache changes.
Test duplicate hashes in two repositories, two revisions sharing a blob,
selection changes, locked files, partial deletion, and unrelated-file retention.

## Execution plan

### Phase 1 — Fix safety and publishing defects

Owner: application and release engineering. Dependencies: none.

1. Implement R1 and add the fixture to `tests/test_model_library.py`. Run the
   model/application suites and the real-cache tests in disposable directories.
2. Extract shared CI validation or otherwise align `windows.yml` and
   `release.yml`: unit/build checks, dependency audits, real clipboard handoff,
   model-library browser lifecycle/accessibility, frozen engine, native windows,
   production build inspection, installation and uninstall.
3. Add the hosted-download verification stage for stable releases. Negative
   tests for changed installer bytes, missing assets, wrong signatures and
   mismatched metadata must leave the release unpublished.
4. Make first-run instructions match the model-library flow. A fresh empty
   cache must reach Ready through Download → Use model/Prepare without relying
   on a developer's cached weights or misleading preparation text.

**Exit:** R1–R3 are closed with regression evidence, first-run smoke passes,
and the corrected source has green required checks. No release tag is pushed.

### Phase 2 — Freeze the candidate and qualify distribution

Owner: maintainer and release engineering. Dependencies: Phase 1.

1. Freeze feature work for this release. Keep model/download/paste recovery
   scope explicit; an arbitrary new model architecture still needs an adapter.
2. Choose a fresh release identity. A practical path is a manual 0.7.0 beta
   followed by stable 0.7.1, if those tags remain unused. This makes stable newer
   than existing local numeric 0.7.0 builds. Alternatively implement proper
   prerelease app versions and test their upgrade ordering. Do not expect a
   numeric 0.7.0 beta to auto-upgrade to numeric 0.7.0 stable.
3. Build one candidate through the normal production pipeline, with the known
   app signing identity and verified frontend assets. Record commit, version,
   installer/shell/engine hashes, catalog revision, build environment and tests.
   Local repair installers with suffixes are not interchangeable evidence.
4. Confirm update-key recovery and CI availability without exposing or rotating
   the shipping private key. Decide whether this release remains explicitly
   unsigned at the Windows level or gets a trusted publisher signature.
5. For a publisher-signed release, sign/timestamp the desktop, engine, Setup and
   embedded uninstaller; verify installed signatures and the downloaded bytes.
   Signing does not guarantee immediate SmartScreen reputation. See
   [Microsoft's guidance](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation).

**Exit:** one immutable candidate, a documented version/update path, and an
accurate distribution/signing claim. An explicitly unsigned beta is allowed;
it must not be presented as publisher-verified.

### Phase 3 — Prove dictation and paste on actual devices

Owner: QA plus a person who can supply physical speech. Dependencies: Phase 2.

Use the candidate on normal-user Windows 10 and Windows 11 installations, with
the precise OS builds recorded. Include a limited-resource CPU machine and a
GPU configuration only if that GPU path is advertised as supported.

| Area | Cases | Acceptance evidence |
|---|---|---|
| Actual insertion | Notepad, Edge plain/rich text fields, VS Code, and the user's actual chat/editor destination | The target receives exactly the final recognized transcript once. Compare target text against VoicePrompt's final transcript, separately from ASR accuracy. |
| Hotkeys/capture | Hold/release and toggle, rapid presses, final syllables, default and USB/Bluetooth microphone where available | No stuck recording, unintended restart or missed release; capture errors remain actionable. |
| Clipboard/focus | Plain/rich text, screenshots, enabled clipboard manager, user copying during speech, focus changing mid-session | No paste to the wrong window; no unrelated newer copy overwritten; recovery actions work. Keep the requested Done wording for the successful path. |
| Long/failed sessions | 30 short sessions, a medium session, a five-minute session, cancellation, unplugged device and terminated worker | No silent transport truncation or duplicate insertion; incomplete recordings are rejected and retry/discard remains usable. |
| Model lifecycle | Fresh download, interrupted/restarted download, selection, delete selected/last model, partial/shared cache removal, restart offline | Correct active model, bounded disk/RAM use, no implicit switch or deletion of unrelated files; an empty library has a clear next action. |
| Performance/recognition | Licensed varied speech, noise suppression on/off, cold/warm startup, CPU and supported GPU | Record WER, p50/p95 finalization latency and peak worker RAM per model/hardware. Approve realistic budgets before making comparative speed/accuracy claims. |

Proposed minimum beta sample: 100 completed dictations across the priority
destinations and the failure cases above. Expand stable acceptance to at least
300 sessions across multiple testers/devices. These are proposed gates, not
claimed results or a guarantee of compatibility with every application.

The existing endurance script only requires nonempty text and no queue overflow.
Add release-specific assertions for captured/submitted/processed sample
accounting, expected stop reason and bounded completion time. Recognizing some
words is not proof that an entire five-minute session was retained. Rerun the
relevant checks whenever capture, worker or insertion code changes.

**Exit:** zero wrong-target pastes, duplicate deliveries, silent transport loss,
unexpected data deletion or unrecoverable recording failures in the acceptance
sample. Record ASR word errors separately; do not promise zero recognition error.

### Phase 4 — Prove upgrades, recovery and accessibility

Owner: QA and release engineering. Dependencies: candidate from Phase 2.
This phase can run alongside Phase 3 on separate test accounts.

1. Test a clean install without Python/developer tools, WebView2 present and
   absent, offline relaunch with cached weights, and startup disabled/enabled.
2. Install real 0.6.3 with synthetic settings/history/planner data/model caches,
   then upgrade to the candidate. Verify schema 7 → 8 backups and actual saved
   records. Existing installer CI reinstalls the same version and checks a saved
   marker; it does not establish this cross-version migration.
3. Exercise cancellation, network interruption, damaged installer/signature,
   insufficient disk space and an installation failure in a disposable account.
   Show a clear state and keep a usable app/data recovery path.
4. Restore the prior installer and compatible settings backup in the test
   account. Schema-8 settings cannot simply be opened by an older app; document
   the actual restoration steps and keep all user data/model caches intact.
5. Test the signed candidate handoff in an isolated updater harness without
   changing the production feed. After guarded publication, verify the actual
   0.6.3 production-feed update on a maintainer machine before announcing it.
6. Check keyboard-only operation, Windows Narrator, focus order, themes and DPI
   at 100%, 125%, 150% and 200%. Confirm the island does not steal typing focus.

**Exit:** clean-machine lifecycle and recovery records exist for the supported
OS matrix. Do not run destructive installer tests against a normal user profile.

### Phase 5 — Commission the catalog and prepare public materials

Owner: maintainer, model maintainer and documentation. Dependencies: Phases 1–2.

1. Review and sign the seed catalog using the existing identity. Configure its
   review requirements, publish the catalog, and verify real refresh, offline
   fallback, bad signature rejection and rollback rejection. If deferred for
   beta, clearly say that only the bundled model list is currently available.
2. Define the ongoing addition process: compatible engine/format, pinned files,
   hashes, model-specific terms, benchmark and reviewer, then signed publication.
   New open weights do not automatically imply engine compatibility. General
   custom imports are a separate feature unless explicitly added to scope.
3. Review the exact redistributed software, native runtime downloads and model
   terms; keep the existing notices and required attribution with the bundle.
   No license violation was established by this review; the missing item is a
   recorded review for the final artifacts and supported models.
4. Add channel-specific release notes, installation/troubleshooting/recovery
   instructions, minimum tested hardware and supported Windows builds. Correct
   older privacy wording and distinguish CI evidence from manual acceptance.
5. Retain release acceptance evidence beyond the current one-day CI expiration:
   commit/version, checksums, catalog, audits, test matrix and reviewer/date.
   Keep fixture screenshots; do not attach customer speech, transcripts or keys.
6. Verify branch/tag protections and a deliberate release-review path. Preserve
   the ability to produce a signed corrective update with the existing key.

**Exit:** users can identify the exact installer, understand its signing and
model limitations, recover their data, and report a problem without sharing
private transcripts. Maintainers can reproduce and review the release.

### Phase 6 — Controlled beta, then stable promotion

Owner: release maintainer. Dependencies: preceding beta/stable gates as applicable.

1. For beta, require R1 fixed, applicable pipeline integrity checks, a checksum-
   matched candidate, first-run/paste/lifecycle smoke on actual devices, accurate
   notes and recovery guidance. Publish as a prerelease outside the stable feed.
2. Collect a small real-user/device pilot, recording version, model, target app,
   driver and failure reason without collecting speech/text by default. Triage
   every missing/partial-paste report and reproduce it before closing it.
3. For stable, require all P0 gaps closed, the supported device/lifecycle matrix
   completed, the catalog feature either commissioned or accurately scoped,
   and no unresolved high-severity data-loss/insertion/recovery defect.
4. Publish only the verified draft artifacts; independently download and verify
   their final bytes before promotion. Verify the public feed on a maintainer
   machine and then announce the release.
5. If a release is faulty, retain its identity and ship a newer corrective
   version. Do not replace public installers or reuse tags. Pause promotion of
   an unsafe model entry and preserve installed, previously valid revisions.

## Evidence record required for sign-off

Each case records: case ID; source commit; app/catalog/model versions; installer
SHA-256; OS/build and normal/admin elevation; microphone/driver/CPU/RAM/GPU;
destination app; expected/observed result; fixture-based evidence; tester/date;
linked defect and retest result. Use `pass`, `fail`, `not run` or `not applicable`.
Do not mark an unknown hardware outcome as passed because a unit test exists.

Implementation starts with R1, then common release checks and hosted-byte
verification. Publisher identity work and device access can proceed in parallel;
neither should delay the repository-scoped deletion fix.
