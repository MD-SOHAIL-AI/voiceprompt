# VoicePrompt 0.7.1 RC 1

This candidate contains the model library, recording and paste fixes developed
after 0.6.3. Install this preview manually. It is excluded from the stable update
feed. A future stable 0.7.1 will upgrade both this candidate and earlier 0.7.0
test builds; published files and version tags must never be replaced.

## Models

Choose among eight reviewed profiles in Settings. Download only the models you
want, then choose **Use model**. Downloads support progress, cancellation,
resuming and file-hash verification. Cached models work offline. Deleting the
selected model unloads it and pauses dictation until another model is selected.

Shared-cache deletion now scopes its plan to the selected repository before
deleting a revision. This fixes a defect where identical commit IDs in different
Hugging Face repositories could cause the wrong cache to be removed. Unrelated
repositories and other revisions are preserved. A nested-file discovery issue
is also fixed.

New supported profiles can arrive through reviewed, signed catalog metadata.
A newly published model still needs a compatible runtime and validation before
it can appear. The catalog does not execute downloaded code or install models
automatically. The bundled list remains available when the service is offline.

## Dictation and setup

- Windows clipboard delivery waits for the destination to consume the transcript
  before restoring the previous clipboard. Delayed reads, clipboard monitors,
  large screenshots and external clipboard changes have regression coverage.
- Recordings account for all queued audio and the release tail. Failed or empty
  recognition keeps audio in memory for retry; incomplete audio is not presented
  as a successful full recording.
- Successful insertion says **Done** in the floating window. Copy says **Copied**.
  When insertion needs attention, recovery stays available instead of disappearing.
- Production installers embed the interface and reject shells that depend on a
  development server. This addresses the localhost connection error.
- First-run setup explains downloading and selecting a model. Prepare is disabled
  until the selected model is installed, and dismissed setup can be reopened.

## Release verification and remaining acceptance

Main and stable builds share Python, clipboard, browser, model-lifecycle and
dependency checks. Stable publication has a separate production approval stage;
uploaded bytes and the update signature must verify before publication. Test
evidence is retained for 90 days. Preview builds also verify uploaded bytes.

Automated tests use synthetic data and licensed public speech. They do not
certify physical microphone/hotkey behavior, all destination applications,
screen readers, or clean Windows 10 and Windows 11 hardware. See the
[release readiness record](release-readiness-plan-0.7.md) for current results.
Broad stable release remains held until outstanding device acceptance is recorded.

Publisher signing and SmartScreen remain deferred. These preview executables
are not Authenticode signed. The existing cryptographic update identity is
preserved. Speech processing remains local; saved user data survives upgrades
and uninstall. Application and dependency licenses are included in the package.
