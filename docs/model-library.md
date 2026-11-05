# Model library and dictation recovery

This source update adds Settings → Models. It has not published an app release
or changed an installed copy of VoicePrompt.

## Installing, switching, and deleting

Available lists supported local speech models; Installed filters downloaded
weights. Download verifies every artifact against its pinned size and SHA-256.
Use model verifies the files, unloads the previous worker, and prepares the new
model. Downloading never silently changes the active model. Preparation can also
install the app-pinned Nemotron runtime or Parakeet speech detector when missing.

Downloads pause while dictation or preparation is busy. Cancel keeps partial
files for retry; Delete partial download removes them. Deleting the selected
model unloads it and clears readiness. Deleting the last model is allowed after
the warning; downloading and selecting another model restores dictation.

New weights live in `%LOCALAPPDATA%\VoicePrompt\models\library`. Legacy
Hugging Face and Moonshine caches are discovered in place. Their Delete action
requires an explicit shared-cache confirmation because other apps may use the
same files. It removes the specified model revision, never the entire cache.
Disk usage is separate from RAM. Once available, measurements show peak speech
worker RAM and the latest finalization time on this device; these are observations,
not cross-model accuracy rankings or latency guarantees.

## Adding supported models to the catalog

The bundled catalog is `voiceprompt/assets/model-catalog.json`. Every artifact
needs a pinned revision, exact size, SHA-256, HTTPS source, license and engine.
Do not reuse an installed model identity for different weights. Publish a new
identity and increment the catalog version. Display metadata may be improved
without replacing weights. A new architecture requires an app adapter and app
release; a catalog cannot install executable code.

`scripts/build_model_catalog.py` regenerates the seed from existing local caches
and the installed Moonshine native manifest, without downloading weights.
Before publishing additions, verify upstream licensing and perform recognition
and hardware acceptance. `scripts/sign_model_catalog.py` uses the existing
protected app update signing identity and never prints it.

The **Publish reviewed model catalog** Actions workflow signs and uploads the
reviewed file to the `model-catalog` prerelease. Configure the `model-catalog`
environment's review requirements before publishing. This prerelease is excluded
from app updates. No workflow or release was dispatched by this source change.

The native shell checks that feed at most daily and offers manual Refresh list
and an opt-out. It verifies signatures before importing entries or replacing the
last valid cache. Offline or unavailable feeds retain the bundled/last verified
list. Model downloads and deletions always remain user actions. Existing custom
Whisper configurations keep their compatibility path; new custom imports and
cloud services are outside this release.

## Dictation delivery

Paste sent means Windows accepted the shortcut, not that every destination
accepted the text. When insertion needs attention, the floating island remains
visible and opens Dictation, which offers Paste to previous app, Copy, and an
explicit Paste and replace clipboard action when preservation is unsupported.
Focus restoration occurs only for the user's explicit paste recovery action.
Uncertain paste attempts are never automatically repeated.

Clipboard restoration no longer uses a 250 ms deadline. A message-pumping owner
publishes delayed Unicode text and restores supported prior formats after an
attributable destination read completes. When consumption cannot be attributed
(for example, a clipboard manager reads first), the transcript remains on the
clipboard and Restore previous clipboard is offered. A newer user copy is kept.

Retry recognition retains one complete recording in memory, including after a
nonempty result. It is cleared when another recording starts, on discard, or on
exit. Audio is not automatically written to disk. Sample accounting guards the
capture → queue → processing → worker handoff; it does not guarantee that a speech
model recognizes every spoken word.

## Verification

Run the Python suite, frontend tests/build, Rust tests/Clippy, and
`scripts/check_engine_bridge.py`. Additional checks:

- `desktop/scripts/check-model-library.mjs`: browser lifecycle, recovery, layout,
  and accessibility; requires the local Vite server on port 1420.
- `scripts/check_model_library_models.py`: offline public-speech replay through
  installed catalog weights, one worker at a time, without microphone or clipboard.
- `scripts/check_clipboard_handoff.py`: real delayed rendering in a private Windows
  window station. Fails before clipboard access if isolation is unavailable.

Physical microphone/hotkey behavior, target-app paste, clipboard-manager
interoperability, elevated destinations, Windows 10/11 installation, and broad
accuracy/latency qualification remain release acceptance gates. See
`production-release-gates.md`. A passing mocked or browser-preview test does not
establish these hardware results.
