# Speech model comparison on this laptop

Research and local measurements: 8 October 2026. The objective is accurate, responsive
English dictation in VoicePrompt, entirely on this Lenovo laptop. The benchmark baseline
is Parakeet TDT v2 int8. The subsequent [Nemotron implementation](nemotron-upgrade.md)
adds production installation, settings, and an isolated native worker; the measurements
below describe the initial research probes unless stated otherwise.

## Recommendation

The strongest tested replacement candidate is **Nemotron Speech Streaming English 0.6B,
Q8_0, using NVIDIA's native Vulkan runtime on the integrated Radeon**. Preserve one stream
for the entire push-to-talk session, and warm up with speech before showing readiness.
The 560 ms configuration improved recognition while avoiding full-clip decoding on release.
This is a recommendation for this application's pipeline and laptop, not a claim that
Nemotron wins every public accuracy benchmark.

Nemotron is now a selectable application backend with verified runtime/model installation,
speech warmup, stream cleanup/cancellation, and explicit Vulkan/CPU settings. The
implementation report records production verification separately, including memory-pressure
failures observed during integration.

## Laptop constraints and benchmark baseline

| Item | Observed configuration |
| --- | --- |
| Laptop | Lenovo 82KD, Ryzen 5 5500U, 6 cores / 12 logical processors |
| Memory | 8 GB installed, 5.85 GiB visible to Windows |
| Graphics | Integrated AMD Radeon; Vulkan is detected, no NVIDIA CUDA device |
| Benchmark recognizer | Parakeet TDT 0.6B v2, int8, sherpa-onnx 1.13.8 |
| Other installed recognizers | Moonshine Voice 0.1.5, faster-whisper 1.2.1 |
| Baseline preset | 4 CPU threads, English, noise suppression off, cloud cleanup none |
| Capture | WASAPI Realtek microphone array, native 48 kHz resampled to 16 kHz |
| Hotkey | Right Ctrl |

Memory pressure matters. Earlier inspection found roughly 0.6–0.9 GiB free under the
normal workload. During the Qwen 1.7B CPU test, free physical memory briefly fell to
about 37 MiB. That model's measured delay includes the consequences of running on this
actual constrained system; it is not an estimate from a desktop GPU benchmark.

## What was tested

The accuracy comparison uses five spontaneous Indian English clips from five different
speakers: 63.12 seconds and 183 reference words. Selection took the first five distinct
speakers with clips lasting 8–25 seconds from the public preview, before seeing any
model's output. [VoiceArena's public MonsoonASR corpus](https://huggingface.co/datasets/VoiceArena/MonsoonASR-Open-ASR-leaderboard-en-IN)
is licensed CC BY 4.0. Only those public recordings were downloaded; no personal audio
or transcripts were uploaded.

Word errors use VoicePrompt's existing case-insensitive word tokenizer and edit distance.
Punctuation is ignored; fillers, contractions, and word splits can still count as errors.
These scores are internally comparable and are not equivalent to the leaderboard's
normalization. Five clips are a useful screening sample, not a statistically established
ranking or a guarantee for the user's voice.

Two timing methods are kept separate:

- **Total decoding time:** feed the recording as fast as possible and measure all work.
  This is useful for compute cost. For streaming recognizers it is not the delay after
  releasing the hotkey, because much of that work happens during speech.
- **Real-time replay:** feed audio at microphone pace through the actual `DictationSession`,
  including resampling, the two-second queue, and 180 ms release tail. Report measured
  release-to-final time; estimated release-to-paste adds 140 ms. This does not time a
  physical microphone or GUI paste.

Candidates run sequentially in separate processes. The normal VoicePrompt process remains
running, and normal laptop load can vary. Qwen and Granite use transcribe.cpp 0.3.1;
Parakeet uses the application backend. NVIDIA's native NeMo-Speech.cpp 0.2.0 provides
Nemotron streaming. CPU runs use four threads for Parakeet/Qwen/Granite and the runtime
default for Nemotron. The native ASR C ABI does not expose a CPU thread-count field.

The separate noise smoke test contains one 10-second narration, a copy mixed with
synthetic Gaussian noise, and two seconds of noise alone. The filename `fan.wav` is
historical: it is not recorded fan or traffic noise. It cannot establish real-world noise
performance by itself.

## Context loss in the current application

Keeping the exact same Parakeet weights but decoding the complete clip reduced errors
from **26/183 to 14/183** in the accelerated comparison. This is strong evidence that
phrase segmentation contributes to the current accuracy problem.

The current backend decodes phrases independently and forces a split after ten seconds
of continuous speech. Later phrases lose earlier sentence context. Making the whole
recording one offline decode restores context but leaves about 3.10 seconds of median
decoding until release on these clips. Simply choosing a larger model does not address
that tradeoff.

The replacement should preserve encoder and decoder state throughout a push-to-talk
session, including pauses, then finalize once on release. Nemotron English has native
cache-aware streaming and offers 80, 160, 560, and 1120 ms processing chunks. The tested
560 ms setting provides a sensible starting point for accuracy and compute cost.
[NVIDIA model documentation](https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b)

## Local accuracy and compute cost

All rows below use the same five conversational recordings. Times are total decoding
work, **not release-to-paste latency**.

| Candidate / configuration | Errors / 183 words | Local WER | Median total decode | Processing time / audio time | Peak process working set |
| --- | ---: | ---: | ---: | ---: | ---: |
| Current Parakeet, separate phrases | 26 | 14.21% | 3.44 s | 0.261 | 838 MiB |
| Same Parakeet, complete clip | 14 | 7.65% | 3.10 s | 0.215 | 780 MiB |
| Nemotron English Q8, CPU, native streaming | 15 | 8.20% | 4.67 s | 0.341 | 981 MiB |
| Granite 5.0 TurboCTC Q8, CPU | 25 | 13.66% | 3.77 s | 0.271 | 619 MiB |
| Qwen3-ASR 0.6B Q8, CPU | 16 | 8.74% | 7.83 s | 0.590 | 1506 MiB |
| Qwen3-ASR 1.7B Q4_K_M, CPU | 18 | 9.84% | 19.92 s | 1.417 | 1779 MiB |

Qwen's native context allocation was limited to 1024 tokens for these short recordings,
rather than using the large default context. Even with that adjustment, its CPU results
do not meet the latency objective. The larger quantized model also did not beat the
smaller model's accuracy in this sample. Granite was lighter but made nearly as many
errors as the current Parakeet phrase pipeline.

## Real-time replay and startup behavior

Replaying through 48 kHz input/resampling slightly changes the Parakeet result, so this
table uses the real-time results for both models, rather than mixing accuracy from the
accelerated and microphone-paced tests.

| Configuration | Conversation errors / 183 | Median release-to-final | Estimated release-to-paste | Failed clips across speech/noise |
| --- | ---: | ---: | ---: | ---: |
| Current Parakeet CPU | 27 | 0.904 s | 1.044 s | 0 / 8 |
| Nemotron CPU, 20 ms feeds, silence warmup | 15 | 0.786 s | 0.926 s | 0 / 8 |
| Nemotron Vulkan, 560 ms model chunks, speech warmup | 14 | 0.630 s | 0.770 s | 0 / 8 |
| Nemotron Vulkan, 160 ms model chunks, speech warmup | 14 | 0.722 s | 0.862 s | 0 / 8 |

The prepared Vulkan run made **48% fewer conversational word errors** and reduced
estimated median release-to-paste delay by **26%** compared with the current Parakeet
run. Its synthetic-noise narration had 0/30 errors versus Parakeet's 5/30; both returned
empty text for noise alone. This does not establish performance on recorded fan/traffic.

A **67.12-second continuous replay**, joining the five different speakers with one-second
gaps, passed without queue or input overflow. Nemotron made 16/183 errors, finalized
0.617 seconds after release, and reached at most 0.30 seconds of queued audio. Processing
used 0.304 seconds per second of audio. This tests sustained state retention and throughput
on varied speech, rather than repeating the same clean sentence.

The nominally faster **160 ms** mode did not reduce release delay on this integrated
GPU. It used 0.645 seconds of processing per second of conversational audio versus
0.294 for 560 ms mode, and made one error in each narration sample rather than zero.
Its continuous replay also passed, but consumed 45.62 seconds of processing versus
20.38 seconds for the 560 ms setting, with the same 16/183 stress errors. The 560 ms
mode therefore remains the recommendation: shorter model chunks are not automatically
faster end to end on this hardware.

The default CPU runtime offered only about 11% less median release delay in that run.
Another CPU run with 100 ms feeds overflowed the two-second queue on one conversation.
The unprepared Vulkan run also overflowed on its first speech clip. Faster successful
clip medians do not erase these failures; those configurations should not be promoted.

Warmup with silent audio exercises mostly blank-token paths. Warming with public speech
before measuring readiness exercised nonblank recognition paths and device kernels; its
transcript and stream state were discarded. That adjustment removed the early failure
in the subsequent Vulkan replay. This supports requiring representative speech warmup,
although one repeat cannot establish that it eliminates every possible scheduling stall.
That warmup took 7.47 seconds after loading the recognizer; it belongs in startup readiness,
not in the measured dictation delay.

Vulkan memory needs special interpretation on this laptop. CPU process memory alone
does not account for graphics allocations. A Windows GPU-memory snapshot during the
speech-warmed run reported approximately **927 MiB dedicated GPU allocation and 97 MiB
shared allocation**. The APU uses system memory for graphics; a small process working
set is not the model's total memory cost. The prepared Vulkan process peaked at 264 MiB;
the graphics allocation values above are a snapshot, not peaks or values to add blindly
to the process working set. Approximately 652 MiB of visible system RAM was free at that
snapshot, with the current app and the research process both running.

## Priorities for the production pipeline

These priorities informed the implementation linked above. Vocabulary boosting and
physical microphone-to-paste comparison remain follow-up accuracy/timing work.

1. Add a native Nemotron backend using the tested Vulkan runtime, pinned Q8 weights,
   and one recognizer loaded before dictation. The runtime supports a C ABI suitable for
   Python's existing worker; no hosted transcription or heavyweight PyTorch environment
   is needed. [NVIDIA's native runtime](https://github.com/NVIDIA/NeMo-Speech.cpp)
2. Warm both silence and representative speech before marking the backend ready. Close
   the warmup stream and discard its text/state. Report startup separately from dictation
   delay; silently warming an unprepared model on the first user request defeats the goal.
3. Maintain one stream from press to release, including pauses. Feed roughly 100 ms
   blocks, retain native encoder/decoder context, and finalize once. Keep the current
   cancellation, bounded queue, and discard-on-overflow behavior. Do not increase the queue
   limit to hide inference stalls.
4. Make Vulkan device selection explicit and expose runtime failures. The implementation
   uses one verified Vulkan SDK for both modes, explicitly disabling GPU execution for CPU.
   Selecting CPU changes latency and memory.
   Load only the selected backend in normal use, rather than keeping multiple models resident.
5. Leave RNNoise and cloud cleanup off for the initial native preset. Native streaming
   passed the synthetic-noise test without suppression. Real fan/traffic conditions still
   need direct comparison before enabling a denoiser, which can remove soft speech.
6. Keep dictionary replacements narrow and investigate bounded recognition hints for
   frequent proper names. Measure incorrect insertions as well as name recall. Vocabulary
   support is a separate accuracy improvement from changing the general speech model.
7. Keep the existing WASAPI capture path and release tail initially. After integration,
   measure actual microphone-to-paste timing before reducing the tail: replay estimates
   cannot establish how much final speech a shorter capture window would lose.

The first priority is context preservation and prepared native inference. A large offline
model on this CPU adds seconds after every release, even when its public benchmark quality
is strong. These measurements do not justify promising a universal 50% latency reduction
or perfect recognition in loud noise.

## Published evidence and alternatives

The public Open ASR results snapshot dated 2 October 2026 gives these Indian English WER
values. Smaller is better; these are published model results, not measurements of our
quantized Windows runtimes.

| Model | Published Indian English WER |
| --- | ---: |
| Qwen3-ASR 1.7B | 3.50% |
| Parakeet TDT v2 | 3.89% |
| Whisper large-v3 | 3.95% |
| Parakeet TDT v3 | 4.14% |
| Qwen3-ASR 0.6B | 4.23% |
| Nemotron English 0.6B | 4.44% |
| Granite Speech 5.0 TurboCTC Apache | 4.75% |
| Whisper large-v3-turbo | 4.77% |
| Nemotron 3.5 multilingual | 7.30% |

[Open ASR leaderboard](https://huggingface.co/spaces/hf-audio/open_asr_leaderboard),
[pinned public results CSV](https://huggingface.co/datasets/hf-audio/open-asr-leaderboard-results/resolve/c23ca4f10e5f1a77c9fd3b41e17cd06a04f0f56c/english_short_latest.csv).
The eight-dataset public average uses the newer cleaned tests and MonsoonASR; it should
not be mixed with older model-card averages using different datasets. Published throughput
also does not measure this laptop's dictation delay.

These results do **not** establish Nemotron as more accurate than full-context Parakeet.
Its attraction here is retaining context while processing continuously. Updating Parakeet
v2 to v3 alone has no clear English accuracy advantage in this snapshot.

Qwen 1.7B is a stronger accuracy candidate on more capable hardware. IBM's published
far-field comparison also favors it over Parakeet v2 in difficult low-SNR conditions,
but that is a different corpus and hardware setup.
[Granite's model card and noise comparison](https://huggingface.co/ibm-granite/granite-speech-5.0-470m-turboctc)
The tested native Qwen port supports CPU/Vulkan but currently exposes offline recognition,
so its complete decode remains after release.
[Native Qwen runtime documentation](https://github.com/handy-computer/transcribe.cpp/blob/main/docs/models/qwen3-asr.md)

Whisper large-v3-turbo reduces decoder depth to speed up Whisper, but remains an offline
model and was not benchmarked on this laptop during this comparison. Its published English
scores do not justify assuming it will improve both accuracy and latency here.
[OpenAI model card](https://huggingface.co/openai/whisper-large-v3-turbo)

Nemotron 3.5 adds multilingual coverage. NVIDIA itself recommends the English checkpoint
for English-only transcription, so a newer version number is not a reason to select 3.5.
[NVIDIA's English-only recommendation](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b)

TheStageAI's improved Whisper Turbo was considered, but its supported encrypted CUDA
and Apple deployment paths do not provide a suitable plain Windows CPU replacement for
this laptop. [Deployment documentation](https://huggingface.co/TheStageAI/thewhisper-large-v3-turbo)

## Local artifacts and reproduction

Public WAVs, references, scripts, downloaded runtime metadata, and full result JSONs live
under the ignored `evaluation/research/` directory. Model weights use the Hugging Face
cache. Research bindings were installed into `evaluation/research/python-binding`, without
changing the application's Python dependencies. Downloaded weights and native archives
were verified against their SHA-256 digests before loading.

Pinned models:

| Candidate | Quantization | Revision |
| --- | --- | --- |
| NVIDIA Nemotron English | Q8_0 | `ebe59e5a817142986528bbbee5dba8db7b38ed50` |
| handy-computer Granite TurboCTC | Q8_0 | `2b0b44d0d6c8b94a2e4f04a2cf3ec6a5c054463b` |
| handy-computer Qwen 0.6B | Q8_0 | `28c66fba077f1359a42b52c55b618a24cdb6e0e7` |
| handy-computer Qwen 1.7B | Q4_K_M | `3555bd238a8572bbace3ebf60d23b036dc0a5dbe` |

The 1.7B model uses heavier quantization to fit memory. Differences between these ports,
precisions, and the original published models may affect accuracy as well as performance.

```powershell
.\.venv\Scripts\python.exe evaluation\research\compare_local.py parakeet-phrases
.\.venv\Scripts\python.exe evaluation\research\compare_local.py parakeet-full
.\.venv\Scripts\python.exe evaluation\research\compare_local.py granite
.\.venv\Scripts\python.exe evaluation\research\compare_local.py qwen-small
.\.venv\Scripts\python.exe evaluation\research\compare_local.py qwen-large
.\.venv\Scripts\python.exe evaluation\research\replay_native.py parakeet
.\.venv\Scripts\python.exe evaluation\research\replay_native.py nemotron --chunk-ms 20
.\.venv\Scripts\python.exe evaluation\research\replay_native.py nemotron --device vulkan --chunk-ms 100
.\.venv\Scripts\python.exe evaluation\research\replay_native.py nemotron --device vulkan --chunk-ms 100 --speech-warmup --stress
.\.venv\Scripts\python.exe evaluation\research\replay_native.py nemotron --device vulkan --chunk-ms 100 --speech-warmup --right-context 1 --stress
.\.venv\Scripts\python.exe evaluation\research\replay_native.py nemotron-production --device vulkan --chunk-ms 100 --stress
```

Run these serially. They replay public audio and never capture the microphone, paste text,
or change VoicePrompt settings.
