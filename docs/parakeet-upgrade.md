# Parakeet replacement for Moonshine

For the subsequent conversational accuracy investigation and newer model candidates,
see the [October model comparison](model-comparison-2026-10.md). The smoke checks below
do not establish accuracy for varied spontaneous dictation.
The subsequent [Nemotron implementation](nemotron-upgrade.md) preserves native streaming
context across an entire recording; this page records the earlier Parakeet change.

The user rejected Moonshine's recognition quality and requested a faster, more accurate
replacement. VoicePrompt now supports **Parakeet TDT 0.6B v2**, an English model running
locally through sherpa-onnx 1.13.8 on CPU with int8 weights. No transcription API is used.
The existing Whisper and Moonshine settings remain available.

NVIDIA describes this model's English training corpus as roughly 120,000 hours of speech.
The Windows CPU conversion and runtime are provided by the sherpa-onnx project.
[NVIDIA model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2),
[sherpa-onnx model documentation](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/nemo-transducer-models.html#sherpa-onnx-nemo-parakeet-tdt-0-6b-v2-int8-english)

## How the delay is reduced

Parakeet itself is an offline model. VoicePrompt's speech detector identifies completed
phrases, which are decoded on the existing worker while recording continues. Release
flushes the remaining phrase and pastes the final transcript once. This reduces the work
left until release without pasting provisional text.

A 250 ms leading context preserves quiet initial syllables that the detector can otherwise
cut off. Already decoded audio is excluded from subsequent phrase context. Audio history
is bounded at 12 seconds and a continuous phrase is limited to 10 seconds. The existing
two-second queue limit, microphone failure checks, cancellation, and deferred settings
continue to protect final insertion.

## Measurements on the Ryzen 5 5500U

The public smoke corpus uses a 10-second narration excerpt, a copy with synthetic Gaussian
noise, and noise-only audio. Each spoken clip has 30 reference words. These are not the
user's voice or real recordings of a fan or traffic.

| Configuration | Clean word errors | Noisy word errors | Estimated median release-to-paste | Peak process RAM |
| --- | ---: | ---: | ---: | ---: |
| Existing Whisper base.en, beam 3 | 0 / 30 | 16 / 30 | 3.620 s | 367 MiB |
| Previous Moonshine Tiny | 1 / 30 | 5 / 30 | 1.089 s | 212 MiB |
| Parakeet, suppression off | 0 / 30 | 5 / 30 | 0.826 s | 818 MiB |
| Parakeet, RNNoise on | 0 / 30 | 1 / 30 | 1.604 s | 880 MiB |

Parakeet without suppression completed the speech replays with a maximum queue backlog
of 0.84 seconds and a processing factor of 0.241. It returned no text for noise-only audio.
It improved the clean excerpt relative to Tiny while retaining the same noisy word-error
count, and improved both latency and noisy word errors relative to the Whisper baseline.

A 60-second stress replay repeated the public excerpt six times. Parakeet made zero word
errors across 180 words, with no queue overflow, 0.82 seconds maximum backlog, and
0.839 seconds estimated release-to-paste latency. Peak process memory was 785 MiB.
This verifies sustained processing for that sample, rather than varied conversational speech.
The full result is in `evaluation/stress/parakeet-results.json`.

Suppression improved the synthetic-noise result but its noisy clip took 2.24 seconds from
release to final text, versus 0.68 seconds without suppression. The faster preset leaves
suppression off. The RNNoise option is retained for conditions where its accuracy benefit
is more valuable than the added delay.

Timings use real-time WAV replay through the same session code and add an estimated
140 ms paste overhead. They exclude silence-only clips from the speech median. They do
not measure rendering in the destination application, and cross-run system load can vary.
The larger model uses substantially more memory than Moonshine.

Detailed results are local under `evaluation/smoke/parakeet-context-results.json` and
`evaluation/smoke/parakeet-context-noise4.json`. Public sample checks support the replacement,
but cannot guarantee accuracy for every voice, name, accent, or background noise. The
automatic corpus-based selector still requires a complete personal test set and never
changes settings; the live replacement is the user's explicit request.

## Configuration and validation

Choose `parakeet` in Settings → Dictation. The fast preset uses four CPU threads, English,
cloud cleanup `none`, and suppression off. Dictionary replacements run on final text;
this greedy Parakeet decoder does not boost vocabulary hints. Whisper-specific model,
beam, and silence-filter controls apply when Whisper is selected.

The converted weights are pinned to revision
`1ab9323565ddb038682214b292f588070a538ce2`. Each cached file is checked for its expected
size before native loading, and the speech detector is checked against a SHA-256 digest.
Valid local caches work without network access. Missing weights are downloaded on first use.

All 57 regression tests pass, including preserving phrase starts, final-tail decoding,
discarding partial output on failure/cancel, bounded audio history, repairing incomplete
model files, rejecting invalid detector downloads, config migration, and the real Tk
settings save with Parakeet selected. Existing capture and insertion tests also pass.

The replacement is applied to the live configuration and VoicePrompt has been restarted.
Its readiness event confirms `parakeet-tdt-0.6b-v2-int8`, four CPU threads, Windows WASAPI,
and no model fallback. Startup warmup took 7.83 seconds; this happens before dictation.
The driver uses its native capture rate with explicit resampling to the model's 16 kHz.
A separate real microphone session completed with zero input or queue overflows and
22 ms reported driver input latency. Package dependency and compilation checks passed.
Right Ctrl, the microphone selection, and existing dictionary replacements were retained.
The original configuration is backed up at
`%LOCALAPPDATA%\VoicePrompt\config.before-parakeet-upgrade.json`.

The earlier Distil result was investigated separately: removing both the vocabulary prompt
and hotword hints eliminated clean-sample repetition, but decoding still took about 7 seconds for that clip.
That configuration was not selected as the replacement.
