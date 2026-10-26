# Nemotron English streaming implementation

Implemented on 8 October 2026 in VoicePrompt 0.3.0. This follows the
[laptop model comparison](model-comparison-2026-10.md), which evaluated the user's
accuracy and release-delay concerns with public conversational Indian English.

The user's saved configuration now selects Nemotron Vulkan and the restarted application
reported ready with `nemotron-speech-streaming-en-0.6b-q8-vulkan-560ms`. Actual startup
warmup took 16.53 seconds; WASAPI microphone preparation passed with a reported 22 ms
input latency. Model fallback was false. Right Ctrl, the selected Realtek microphone,
dictionary, startup preference, and clipboard behavior were preserved. The previous
configuration is backed up at `%LOCALAPPDATA%\VoicePrompt\config.before-nemotron-upgrade.json`.

## Selected preset

| Setting | Value |
| --- | --- |
| Speech engine | `nemotron` |
| Model | NVIDIA Nemotron Speech Streaming English 0.6B, Q8_0 |
| Runtime | NeMo-Speech.cpp 0.2.0, Windows x86_64 Vulkan |
| Processing | Vulkan GPU 0, the laptop's integrated AMD Radeon |
| Streaming context | Right context 6, 560 ms model chunks |
| Audio delivery | 100 ms float32 blocks, mono 16 kHz |
| Capture | Existing WASAPI path with stateful native-rate resampling |
| Hotkey | Hold Right Ctrl |
| Startup | Model loading plus silence and licensed public speech warmup |
| RNNoise / cloud cleanup | Off |

[NVIDIA model](https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b),
[native runtime](https://github.com/NVIDIA/NeMo-Speech.cpp).

The 560 ms value is the model's processing chunk, not a guaranteed end-to-end delay.
The public-speech warmup's transcript is discarded; each real recording receives a
fresh stream. Dictionary replacements continue to apply after finalization. Recognition
boosting is not enabled in the native decoder because it was not part of the measured preset.

## Changes in the dictation path

One recognizer stays loaded, and one native stream covers the entire hotkey session,
including pauses. Encoder and decoder state are preserved instead of decoding separate
phrases. Release flushes the final partial input block and finishes the native stream.
Only an authoritative final result can reach the existing paste/history path.

Cancellation, malformed samples, missing final results, microphone failure, and queue
overflow discard the session. The existing two-second audio queue, release tail, and
exactly-once insertion behavior remain active. Changing the model or processing device
waits for an active session to finish, closes the old recognizer, and warms the new one.

Native inference runs in a persistent local helper process. It receives audio through an
inherited Windows pipe; it has no transcription endpoint or network audio upload. Normal
dictation sends 100 ms blocks to amortize pipe overhead. A native assertion, driver failure,
or unresponsive worker resets model readiness and reports an error instead of terminating
VoicePrompt or returning an incomplete transcript. The next warmup starts a fresh helper.

On Windows, the helper starts the actual interpreter with the current environment's
module paths. This avoids importing the whole GUI in the helper and avoids monitoring a
virtual-environment redirector instead of the process owning the graphics allocations.

## Installation and offline behavior

The model is pinned to revision `ebe59e5a817142986528bbbee5dba8db7b38ed50`;
its 699,872,960-byte GGUF is verified with SHA-256 before loading. The official
19,302,464-byte runtime archive and each installed binary are also checked. Cached
corruption triggers repair before native loading. Archive extraction rejects paths
outside the installation staging directory.

Weights use the Hugging Face cache. The runtime and its upstream licenses are installed
under `%LOCALAPPDATA%\VoicePrompt\runtimes\`. Once verified assets are installed,
startup and dictation work offline. The public startup WAV is bundled with the application;
its checksum, audio format, and CC BY attribution are in `voiceprompt/assets/`.

Settings add the engine and a separate `vulkan` / `cpu` processing choice. CPU execution
uses the same verified runtime with GPU disabled and must be selected explicitly. There
is no silent CPU substitution. Other existing settings and recognizers are preserved.

PyInstaller commands in the README include the warmup WAV and hash manifest. Packaged
worker startup branches before normal application argument parsing. Source execution is
validated; a PyInstaller executable has not been built as part of this change.

## Verification and measurement limits

The automated suite covers native-result finalization, cancellation, worker crashes and
timeouts, warmup isolation, variable-sized audio delivery, integrity checks, configuration,
and the application's insertion/recording behavior. Production replay uses the actual
transcriber factory, helper process, and dictation session with 48 kHz input/resampling.

Earlier research measured 14 errors in 183 conversational words with speech-warmed
Nemotron Vulkan, versus 27 with the previous Parakeet phrase pipeline. Estimated median
release-to-paste was 0.770 seconds versus 1.044 seconds. These are small-sample research
measurements; helper-process overhead and system load must be assessed separately.

The final production replay passed all eight short clips plus the 67.12-second continuous
session, with no queue/input overflow or failed clips. Conversation accuracy was again
14/183 errors; clean and synthetic-noisy narration each had 0/30 errors, and noise alone
returned empty text. The continuous session had 16/183 errors, 0.600 seconds from release
to final, and at most 0.34 seconds queued. Across the short clips, the queue peaked at
0.52 seconds, below the two-second limit.

The latest production conversation median was **0.914 seconds to final**, or **1.054
seconds estimated to paste**. This is approximately the earlier Parakeet median, rather
than reproducing the initial research run's 26% delay reduction. These sequential runs
were under changing laptop load; they do not isolate helper overhead or prove a consistent
speed gain. The improvement reproduced here is recognition accuracy and sustained streaming.
The replay process peaked at 84 MiB and its native helper at 206 MiB; neither number
includes graphics allocations or measures the full live tray application's memory.

Validation: **78 automated tests passed**, `pip check` reported no dependency conflicts,
and `git diff --check` passed. Public replay uses the actual production backend/factory;
physical speech-to-GUI-paste timing remains unmeasured.

This laptop has 8 GB installed but only 5.85 GiB visible to Windows. During implementation,
native startup encountered allocation failures while the previous model remained resident;
startup succeeded after that app was closed. Running model replay alongside the full test
suite also exposed a Vulkan device loss under heavy memory pressure. Isolation contains
those failures; it does not guarantee the graphics driver can allocate under every workload.
Verification runs therefore use one loaded model at a time, with regression tests and
model replay performed sequentially.

GPU allocations are separate from app/worker working-set measurements, and the Radeon
shares laptop memory. The evaluator reports the native worker separately and counts both
process peaks for its process-memory comparison; this still excludes graphics allocations.
The research review contains the observed GPU-memory snapshot.

The noise smoke test uses synthetic Gaussian noise, not actual fan or traffic recordings.
No personal speech was uploaded. Accuracy on the user's voice and real noisy surroundings
still needs direct use or a local evaluation corpus.
