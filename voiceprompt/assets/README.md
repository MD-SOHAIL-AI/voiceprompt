# Nemotron startup assets

`start.wav`, `stop.wav`, and `reminder.wav` are original synthesized notification
tones created for VoicePrompt. They contain no recordings or third-party audio.
Regenerate them with `python scripts/generate_sounds.py`. They use quiet sine tones
and smooth fades; final loudness also depends on the Windows output volume.

`nemotron-warmup.wav` is public speech used to warm nonblank recognition paths and
Vulkan kernels before VoicePrompt accepts dictation. Its transcript is discarded and
its stream is closed. It is not a user recording.

Attribution: VoiceArena, **MonsoonASR Open ASR leaderboard, Indian English**, sample
`40631389_215_58_229_71` (14.13 seconds).
[Original dataset](https://huggingface.co/datasets/VoiceArena/MonsoonASR-Open-ASR-leaderboard-en-IN),
[CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/).
Stored as 16 kHz, mono, 16-bit PCM WAV; no speech content was edited.

`nemotron-runtime-hashes.json` contains SHA-256 hashes of the binaries in NVIDIA's
`nemo-speech-0.2.0-windows-x86_64-vulkan.zip`. The official archive SHA-256 is pinned
in `nemotron_assets.py`. Downloaded runtime licenses and documentation are retained
beside the binaries in the user's local cache.
