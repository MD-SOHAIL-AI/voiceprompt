# VoicePrompt 0.7.0

Prepared for local installation. Committing this source does not publish a
GitHub release or change the stable update feed.

The corrected local installer embeds the frontend and opens without a local
development server. If an earlier 0.7.0 installer opens a page saying
`127.0.0.1 refused to connect`, close VoicePrompt and install the corrected
package over it. Release builds now reject development-mode shells, and the
packager verifies the embedded frontend before accepting a supplied executable.

## Included changes

- Settings → Models provides eight pinned local model choices with download,
  cancellation, preparation, selection, and deletion controls. Existing cached
  models are discovered without requiring duplicate downloads.
- Deleting the selected or last model unloads it and clears readiness. Shared
  cache removal requires an explicit confirmation; other model files are kept.
- Model downloads use verified artifacts and pause while VoicePrompt is busy.
  A signed catalog refresh and publication workflow supports future additions.
- Clipboard restoration waits for an attributable destination read instead of
  using a fixed timer. Clipboard changes and successive dictations preserve the
  user's newer content and original snapshot.
- Persistent insertion notices, explicit paste recovery, and retrying the latest
  recording make missing or incomplete output recoverable.
- Audio sample accounting guards capture, queueing, processing, and finalization.
  Failed or cancelled sessions clear pending insertion state.

## Data and compatibility

Settings migrate to schema 8 and preserve a schema-7 backup. Existing model
choices, dictionary, history, and planner data are preserved. Audio stays in
memory and is not automatically saved to disk or uploaded. Returning to an older
app requires restoring the compatible settings backup.

## Verification limits

The implementation passed 222 Python tests (two additional checks skipped),
14 frontend tests, 14 Rust tests, Clippy, source/frozen bridge checks, four frozen
worker import checks, browser model/recovery flows, and eight offline model
replays. Nemotron replay also passed with suppression enabled and disabled.

Native WebView attachment and private clipboard-station testing were unavailable
in the development environment. Physical microphone/hotkey behavior, destination
paste, broad accuracy/latency qualification, and Windows 10/11 installer
acceptance remain manual release gates. Windows publisher signing is separate
from update signing. See [model library](model-library.md) and
[release acceptance](production-release-gates.md).
