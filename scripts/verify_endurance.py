"""Replay licensed public speech at microphone pace; never captures personal audio."""
import argparse
import json
import os
import hashlib
import platform
import subprocess
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
    parser.add_argument("--noise-suppression", action="store_true")
    args = parser.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    import numpy as np
    from voiceprompt.backend_process import ManagedTranscriber
    from voiceprompt.config import Settings
    from voiceprompt.evaluate import ReplayRecorder, process_peak_mb
    from voiceprompt.session import DictationSession
    from voiceprompt.state import StopReason
    if not 1 <= args.seconds <= 300:
        parser.error("Endurance replay must be between one and 300 seconds.")
    settings = Settings(backend=args.backend, nemotron_device="cpu", noise_suppression=args.noise_suppression)
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
        text, duration = session.run(recorder, backend, hotwords="", noise_suppression=args.noise_suppression, on_progress=observed)
        from voiceprompt import __version__
        root = Path(__file__).resolve().parents[1]
        source_hash = hashlib.sha256()
        for path in sorted((root / 'voiceprompt').rglob('*.py')):
            source_hash.update(path.relative_to(root).as_posix().encode())
            source_hash.update(path.read_bytes())
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        report = {"backend": args.backend, "seconds": duration, "wall_seconds": time.perf_counter() - started,
                  "warmup_seconds": warmup, "output_characters": len(text),
                  "parent_peak_mb": process_peak_mb(), "worker_peak_mb": process_peak_mb(backend._process.pid),
                  "metrics": session.metrics,
                  "version": __version__, "source_commit": commit, "python_source_sha256": source_hash.hexdigest(),
                  "os": platform.platform(), "noise_suppression": args.noise_suppression,
                  "fixture_sha256": hashlib.sha256(public_audio.read_bytes()).hexdigest(),
                  "limits": "Public WAV replay; no physical keyboard, microphone, clipboard, or accuracy comparison."}
        expected_samples = round((args.seconds + .18) * rate)
        checks = {
            "nonempty_transcript": bool(text),
            "complete_capture_and_tail": abs(session.metrics['queued_samples'] - expected_samples) <= 1,
            "all_samples_submitted": session.metrics['queued_samples'] == session.metrics['submitted_samples'],
            "all_samples_processed": abs(session.metrics['processed_samples'] - round(expected_samples * 16000 / rate)) <= 1,
            "no_overflow": not session.audio_queue.overflow and recorder.input_overflows == 0,
            "expected_stop_reason": session.stop_reason in (StopReason.RELEASED, StopReason.DURATION_LIMIT),
            "bounded_finalization": session.metrics['release_to_final_seconds'] <= session.finalization_timeout,
        }
        report.update(checks=checks, passed=all(checks.values()))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        if not report['passed']:
            raise RuntimeError("Endurance replay failed; inspect the sample accounting report.")
    finally:
        backend.close()


if __name__ == "__main__":
    main()
