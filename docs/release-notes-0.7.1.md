# VoicePrompt 0.7.1

The model library, recording completeness checks and clipboard delivery fixes
from 0.7.1 RC 1 now use the stable in-app update channel. This version is newer
than 0.6.3, earlier 0.7.0 test builds and 0.7.1 RC 1.

## Update your app

Open **Settings → Check for updates**, choose **Update now**, then select
**Restart to update** after saving your work. Automatic checks also announce the
update when enabled. Resolve active recordings, recognition, pending paste,
retained-audio recovery and unsaved forms before restarting.

Versions older than 0.6.1 need one manual installation of
**VoicePrompt-Setup-0.7.1-x64.exe** from this release. Subsequent releases can use
the in-app updater. Settings, history, dictionary entries, tasks, timers, alarms,
startup choices and cached speech models are preserved.

## What changed since 0.6.3

- Choose among eight reviewed speech-model profiles in **Settings → Models**.
  Download only the models you want, then choose **Use model**. Downloads support
  progress, cancellation, resuming and file-hash verification. Cached models
  work offline. Deleting the selected model pauses dictation until you select
  another model. Shared-cache deletion preserves unrelated repositories and
  revisions, including repositories with identical revision IDs.
- Refresh reviewed, signed model-catalog metadata from GitHub. New entries need
  a compatible runtime; catalog refresh does not install models automatically.
  The bundled catalog remains available offline.
- Clipboard delivery waits for the destination to consume the transcript before
  restoring the previous clipboard. Recovery stays available after failed paste.
  Successful insertion says **Done**; copying says **Copied**.
- Recording checks account for queued audio and the release tail. Failed or
  empty recognition keeps audio in memory for retry. Incomplete audio is rejected
  instead of being presented as a complete recording.
- Setup explains downloading and selecting a model, disables Prepare until the
  selected model is installed, and allows dismissed setup to be reopened.
- Production packages embed the interface, reject development-server shells,
  check embedded Python modules against source and include dependency notices.

## Update authenticity and validation

The attached `latest.json` uses the existing update-signing identity trusted by
installed apps. The app verifies the signature, installer size and SHA-256 before
installation. The release workflow requires source, frontend, Rust, clipboard,
browser/model lifecycle, dependency-audit, frozen-worker, native UI and installer
checks, including an upgrade from 0.6.3. A separate production review precedes
upload; hosted installer bytes and metadata must verify before publication.

Physical microphone and hotkey trials, the full destination-app matrix, clean
normal-user Windows 10/11 lifecycle, screen readers and complete DPI acceptance
remain unverified. Automated tests and public-speech replay do not certify those
outcomes. See the [release record](release-acceptance-0.7.1.md).

Windows binaries remain **unsigned by a Windows publisher** and may show a
SmartScreen or unknown-publisher warning. Cryptographic update signing is
separate from Windows publisher signing.

## Data and recovery

Speech processing remains local. Model downloads, optional contest services,
catalog refresh and update checks use their existing network services. No audio
or transcripts are uploaded by the updater. Application and dependency licenses
are included in the package.

Keep a backup of `%LOCALAPPDATA%\VoicePrompt` before manually returning to an
older version. Version 0.7.1 backs up migrated settings; older engines may not
understand newer data. Restore a compatible settings backup when rolling back.
Uninstall preserves saved data and model caches.
