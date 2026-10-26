"""Replay licensed public speech at microphone pace; never captures personal audio."""
import argparse
import json
import os
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--backend", choices=["nemotron", "whisper", "moonshine", "parakeet"], default="nemotron")
    parser.add_argument("--output", type=Path, default=Path("evaluation/endurance.json"))
    args = parser.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    import numpy as np
    from voiceprompt.backend_process import ManagedTranscriber
    from voiceprompt.config import Settings
    from voiceprompt.evaluate import ReplayRecorder, process_peak_mb
    from voiceprompt.session import DictationSession
    from voiceprompt.state import StopReason
    settings = Settings(backend=args.backend, nemotron_device="cpu", noise_suppression=False)
    backend = ManagedTranscriber(settings)
    public_audio = Path(__file__).resolve().parents[1] / "voiceprompt/assets/nemotron-warmup.wav"
    with wave.open(str(public_audio), "rb") as source:
        audio = np.frombuffer(source.readframes(source.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        rate = source.getframerate()
    audio = np.tile(audio, int(args.seconds * rate / len(audio)) + 1)[:args.seconds * rate]
    session = DictationSession(1)
    recorder = ReplayRecorder(audio, rate, session)
    progress = [0, 0]
    def observed(elapsed, backlog, failed):
        progress[0] = max(progress[0], backlog)
        if int(elapsed) // 30 > progress[1]:
            progress[1] = int(elapsed) // 30
            print(f"Recorded {int(elapsed)}s; recognition backlog {backlog:.2f}s", flush=True)
    try:
        started = time.perf_counter()
        backend.preload()
        warmup = time.perf_counter() - started
        print(f"Prepared {args.backend} in {warmup:.2f}s. Replaying public speech for {args.seconds}s.", flush=True)
        started = time.perf_counter()
        text, duration = session.run(recorder, backend, hotwords="", noise_suppression=False, on_progress=observed)
        report = {"backend": args.backend, "seconds": duration, "wall_seconds": time.perf_counter() - started,
                  "warmup_seconds": warmup, "output_characters": len(text),
                  "parent_peak_mb": process_peak_mb(), "worker_peak_mb": process_peak_mb(backend._process.pid),
                  "metrics": session.metrics,
                  "limits": "Public WAV replay; no physical keyboard, microphone, clipboard, or accuracy comparison."}
        if not text or session.audio_queue.overflow:
            raise RuntimeError("Endurance replay did not return complete text.")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        backend.close()


if __name__ == "__main__":
    main()
