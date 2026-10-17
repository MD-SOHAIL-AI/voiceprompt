# VoicePrompt performance review

This covers the initial implementation. The subsequent user-requested replacement of
Moonshine is documented in [Parakeet replacement](parakeet-upgrade.md), including the
current model choice and newer measurements.

Review and implementation verified on 8 October 2026. The original Whisper `base.en`
selection was retained at deployment. The live settings subsequently selected Moonshine
Tiny, and that selection was preserved during the final microphone fix. Tiny is the strongest
streaming candidate in the local measurements, but has not passed a personal voice
accuracy comparison. Whisper remains available with its saved model and decoding options.

## Laptop and running configuration

| Item | Observed state |
| --- | --- |
| Laptop | Lenovo 82KD, AMD Ryzen 5 5500U, 6 cores / 12 logical processors |
| RAM | 8 GB installed; Windows reports about 5.85 GiB usable |
| Available RAM | About 0.35–0.95 GiB across inspection snapshots; substantial memory pressure |
| GPU | Integrated AMD Radeon; the CTranslate2 CUDA path is unavailable |
| OS | Windows 11 Pro, build 26300 |
| Python | 3.10.6, isolated project `.venv` |
| Tested inference packages | faster-whisper 1.2.1, CTranslate2 4.7.1, moonshine-voice 0.1.5 |
| Tested audio packages | sounddevice 0.5.6, soxr 1.1.0, optional pyrnnoise 0.4.5 |
| Retained Whisper settings | `base.en`, CPU/int8, beam 3, English, 4 CPU threads |
| Backend at initial checkpoint | Moonshine Tiny streaming, English |
| Capture | Realtek microphone array, WASAPI, native 48 kHz, explicit conversion to 16 kHz |
| Cleanup / suppression | Cloud cleanup `none`; RNNoise disabled |

These are tested package pins, rather than a claim that every package is the latest
release. The initial Whisper restart through `.venv` reached ready after an 8.51-second
warmup, with capture preparation taking 0.38 seconds. The final corrected Moonshine Tiny
restart reached ready in 1.94 seconds, with the validated capture preparation taking
0.29 seconds. Both reported 22 ms input latency. Preparation is performed before dictation.
The existing startup entry now uses the isolated environment. The single-instance mutex
was verified against the live app.

The Realtek device rejected the requested 16 kHz WASAPI rate. The recorder successfully
used its native 48 kHz rate instead. The tray reports this rate fallback; it is not a
fallback to another microphone or to MME. Input latency is the driver's reported value,
not a measurement of the complete microphone-to-paste path.

Live use exposed a start failure that opening alone did not reveal. It was reproduced
with the recorder running on a worker thread; initializing Windows COM on that same thread
resolved it. The worker now initializes COM once and balances its release on shutdown.
Preparation also performs a brief start/stop probe with audio retention disabled, so Auto
mode can reject an input path that opens but cannot start before reporting ready. Three
consecutive native captures succeeded after COM initialization, followed by two complete
Moonshine sessions using the real microphone and reused WASAPI stream without drops or
queue overflow. Those short microphone checks verified capture, not spoken-word accuracy.

## Findings and implemented changes

The original recognition pipeline buffered speech and began Whisper decoding after
release. Its release delay cleared the stream reference before waiting, so callbacks
during the intended 180 ms tail stopped retaining audio. That could clip final syllables
while still adding delay. The new recorder retains those frames, decides accidental taps
using the held duration, and reuses an inactive input stream between sessions. It prefers
WASAPI and falls back explicitly when needed.

One worker now owns model and audio operations. Hotkey callbacks signal start/release
without sleeping or decoding. Settings changes wait for the active session, and quitting
cancels pending insertion. Final output is pasted once; partial streaming revisions are
never pasted. Dropped microphone frames, delivery errors, device failure, and recognition
queue overflow reject the recording instead of inserting an incomplete transcript.

The optional Moonshine backend consumes audio while the user speaks. Native calls batch
100 ms of audio to avoid excessive frontend overhead from small driver callbacks. A queue
holds at most two seconds of unprocessed audio. This bounds delay and makes failure visible
when recognition cannot keep up. There is also a 120-second recording limit.

Whisper remains available with its existing decoding settings, actual inference warmup,
beam controls, and CPU thread controls. The tray identifies the model actually loaded and
any fallback reason. The evaluator rejects a requested model that fell back to another one.
The missing Distil-Whisper weights were downloaded and checked through real inference.

Stateful resampling preserves filter history between callbacks. Optional RNNoise processes
48 kHz audio through the bundled native library without importing its Python plotting and
audio stack. The Gemini SDK is also imported only when that cleanup provider is selected.
Model switches close the prior model before loading another, which matters on this laptop.

Clipboard restoration checks both the dictation generation and current clipboard contents,
so an older timer does not overwrite a newer dictation or something the user copied.
The settings window's variables now belong to its own Tcl interpreter, addressing a failure
when the floating pill and Settings are open together.

## Measurements on this laptop

The smoke corpus contains a public narration excerpt lasting 10 seconds, the same excerpt
with seeded Gaussian noise, and a two-second noise-only clip. Each spoken excerpt has
30 reference words. The filename `fan.wav` represents synthetic noise in this smoke corpus;
it is not a recording of a real fan. The stress corpus repeats the clean excerpt six times
to create 60 seconds of continuous speech.

Each candidate used the same audio, vocabulary hints, replacements, English setting, and
capture-processing/session code. Candidates ran sequentially in separate processes. The
latency below is the median of successful speech clips, excluding silence-only clips,
plus a **140 ms estimated paste overhead**. It is not a measured GUI insertion time. Peak
RAM is the evaluation process's peak Windows working set, not total system memory.

| Candidate, suppression off | Estimated release-to-paste median | Clean word errors | Synthetic-noise word errors | Peak RAM |
| --- | ---: | ---: | ---: | ---: |
| Whisper base.en, beam 3 | 3.620 s | 0 / 30 | 16 / 30 | 367 MiB |
| Moonshine Tiny streaming | 1.089 s | 1 / 30 | 5 / 30 | 212 MiB |
| Moonshine Small streaming | Invalid comparison: clean clip overflowed | Failed | 3 / 30 | 356 MiB |
| Distil-Whisper small.en, beam 1 | 8.069 s | 127 / 30 | 111 / 30 | 550 MiB |

Tiny reduced estimated post-release speech latency by about **70%** relative to the
Whisper baseline in this small repeat run. It also used about 42% less peak process RAM.
Those figures describe this corpus and system load, not guaranteed performance for every
utterance. Tiny's one clean error is a 3.33 percentage-point WER regression on this very
small sample, so it does not meet the accuracy gate for automatic recommendation.

Distil repeated words under the tested decoding configuration; insertions can make word
error rates exceed 100%. This configuration is unsuitable based on the observed results.
That does not establish that every Distil configuration or other recording would behave
the same way. Whisper's beam-1 variant alone produced only a modest latency change in the
earlier paired run and did not improve its noisy word errors.

For the 60-second stress replay, Tiny completed with 3 errors in 180 words, 0.842 seconds
from release to final text, a 0.739 processing real-time factor, 1.02 seconds maximum queue
backlog, and 223 MiB peak RAM. A factor below 1 means processing took less time than the
audio duration. Small overflowed the two-second queue and was rejected. Small therefore
is not the recommended streaming option for sustained dictation on this machine.

An earlier paired suppression comparison had mixed results:

| Configuration | Clean errors, raw → RNNoise | Noisy errors, raw → RNNoise | Interpretation |
| --- | ---: | ---: | --- |
| Whisper base.en, beam 1 | 0 → 0 | 16 → 3 | Worth testing with real noise; extra processing cost |
| Moonshine Tiny | 1 → 0 | 5 → 18 | Worse noisy recognition; leave suppression off |
| Moonshine Small | 1 → 1 | 3 → failed clip | Suppressed replay overflowed |

Better-sounding audio did not consistently produce better recognition. Suppression remains
off until a comparison with the user's microphone, voice, fan, and traffic demonstrates a gain.
Technical-name recall has not been validated by this public narration corpus.

Raw recordings and detailed local results are excluded from Git under `evaluation/`:
`smoke/final-results.json`, `smoke/batched-results.json`, `smoke/distil-results.json`, and
`stress/results.json`. The first two report summaries were corrected to exclude silence
from speech latency; their recorded transcripts and timing rows were preserved.

## Research informing the implementation

Moonshine's native toolkit supports Windows and on-device streaming, doing recognition
work during speech. That architecture supports the change to streaming, while the Tiny
versus Small choice above comes from this laptop's measurements. [Moonshine documentation](https://github.com/moonshine-ai/moonshine-v2)

The existing faster-whisper implementation uses CTranslate2 and supports CPU int8
inference. CTranslate2 recommends int8 for CPU performance and controlling thread counts
to avoid contention. A larger beam adds search work; the evaluator compares accuracy before
recommending a reduction. [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[CTranslate2 performance guidance](https://opennmt.net/CTranslate2/performance.html),
[threading guidance](https://opennmt.net/CTranslate2/parallel.html)

RNNoise is a speech noise-reduction library. Its effect on this app's recognition quality
was evaluated separately, rather than assuming noise reduction would improve WER.
[RNNoise project](https://github.com/xiph/rnnoise)

[Microsoft's COM initialization guidance](https://learn.microsoft.com/en-us/windows/win32/learnwin32/initializing-the-com-library)
requires initialization on each thread using COM and a matching uninitialization. The
WASAPI failure and successful recovery were reproduced locally on this laptop.

## Validation and next use

All 47 regression tests pass, including release-tail retention, short taps, variable-size
audio queues, device/overflow errors, cancellation, deferred settings, exactly-once insertion,
stream finalization, clipboard restoration, real native RNNoise processing, and a real Tk
settings save with the floating pill's interpreter present, thread-owned COM cleanup,
and an openable-but-unstartable capture fallback. Dependency checks, Python
compilation, and Git whitespace checks passed. The restarted live app reached ready with
WASAPI capture. After the final correction it uses the current Moonshine Tiny selection;
the original Whisper startup had also been verified without a model fallback.

External-app paste and visual settings interaction could not be automated: the Windows
computer-use native pipe was unavailable. Unit tests verify insertion boundaries, but they
do not prove that the destination application rendered the pasted text. Real fan/traffic
accuracy, the user's accent, power/thermal behavior, and technical-name recognition remain
personal evaluation work. No personal voice accuracy improvement is claimed here.

For the latency option, open Settings → Dictation and choose `moonshine` with `tiny`,
leave suppression off, save, and wait for ready. Returning to `whisper` restores access to
the retained Whisper selection. The CPU thread control applies to Whisper.

Run **Evaluate VoicePrompt.bat** for guided recordings: ten speech clips in each of clean,
fan, and traffic conditions, noise-only audio, and a 65-second stress recording. Correct the
reference text if it differs from what was actually spoken. The evaluator compares models,
noise suppression, and Whisper thread counts locally and never changes app settings.

Recommendation gates require at least 30 speech clips across the three conditions, a
60-second stress clip, at least 50% lower median latency, at least 20% lower relative noisy
WER, no more than one percentage point worse clean WER, no noise-only text, real-time
processing, no failed clips, and a process memory peak below 1 GiB. Confirm the recommended
configuration by dictating into an actual destination app before keeping it selected.

Actual app timing metrics are written to `%LOCALAPPDATA%\VoicePrompt\performance.jsonl`.
They include release-to-final, release-to-paste-command completion, queue backlog, capture
latency, and failures. They contain no audio or dictated text. GUI rendering is not acknowledged
by the paste metric. Existing transcription history still stores text locally. A pre-upgrade
settings backup is available as `config.before-performance-upgrade.json` in the same directory.
