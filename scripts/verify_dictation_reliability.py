"""Offline speech replay through the production worker; no microphone or clipboard."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, help="JSONL with audio paths and reference text")
    parser.add_argument("--backend", choices=["nemotron", "whisper", "parakeet", "moonshine"], default="nemotron")
    parser.add_argument("--device", choices=["cpu", "vulkan"], default="cpu")
    parser.add_argument("--noise-suppression", choices=["off", "on", "both"], default="both")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation/dictation-reliability.json")
    parser.add_argument("--compare-batch", action="store_true", help="Compare Whisper phrase results with whole-recording decoding using the same worker")
    parser.add_argument("--batch-baseline", action="store_true", help="Measure whole-recording Whisper without real-time pacing")
    parser.add_argument("--whisper-phrases", action="store_true", help="Explicitly evaluate opt-in Whisper phrase decoding")
    args = parser.parse_args()
    if args.batch_baseline and args.backend != "whisper": parser.error("--batch-baseline requires --backend whisper")
    os.environ["HF_HUB_OFFLINE"] = "1"

    import numpy as np
    import soxr
    from voiceprompt.backend_process import ManagedTranscriber
    from voiceprompt.config import Settings
    from voiceprompt.evaluate import ReplayRecorder, word_errors
    from voiceprompt.session import DictationSession

    if args.manifest:
        entries = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
        for entry in entries:
            entry["path"] = args.manifest.resolve().parent / entry["audio"]
    else:
        entries = [{"path": ROOT / "voiceprompt/assets/nemotron-warmup.wav"}]
    backend = ManagedTranscriber(Settings(backend=args.backend, nemotron_device=args.device, whisper_phrase_decoding=args.whisper_phrases))
    report = {"backend": args.backend, "device": args.device, "rows": [], "limits":
              "Public/local WAV replay; does not test physical microphone, hotkey, or clipboard delivery."}
    try:
        started = time.perf_counter()
        backend.preload()
        report["warmup_seconds"] = time.perf_counter() - started
        print(f"Prepared {args.backend} in {report['warmup_seconds']:.2f}s", flush=True)
        modes = [False, True] if args.noise_suppression == "both" else [args.noise_suppression == "on"]
        for noise in modes:
            for entry in entries:
                with wave.open(str(entry["path"]), "rb") as source:
                    if source.getsampwidth() != 2 or source.getnchannels() != 1:
                        raise ValueError("Replay requires mono 16-bit PCM WAV files.")
                    audio = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float32) / 32768
                    rate = source.getframerate()
                # Exercise the same 48 kHz input/resampling path as this laptop.
                if rate != 48000:
                    audio = soxr.resample(audio, rate, 48000).astype(np.float32)
                session = DictationSession(len(report["rows"]) + 1)
                row = {"clip": entry["path"].name, "noise_suppression": noise, "audio_seconds": len(audio) / 48000}
                try:
                    if args.batch_baseline:
                        from voiceprompt.audio import AudioProcessor
                        processor = AudioProcessor(48000, noise)
                        try:
                            batch_audio = processor.process(np.concatenate((audio, np.zeros(8640, dtype=np.float32))), final=True)
                        finally:
                            processor.close()
                        before_batch = time.perf_counter()
                        text = backend.transcribe_batch(batch_audio)
                        row["batch_decode_seconds"] = time.perf_counter() - before_batch
                    else:
                        text, _ = session.run(ReplayRecorder(audio, 48000, session), backend,
                                              hotwords="", noise_suppression=noise)
                    row["output_words"] = len(text.split())
                    if "text" in entry:
                        row["errors"], row["reference_words"] = word_errors(entry["text"], text)
                    if args.compare_batch and args.backend == "whisper":
                        from voiceprompt.audio import AudioProcessor
                        processor = AudioProcessor(48000, noise)
                        try:
                            batch_audio = processor.process(np.concatenate((audio, np.zeros(8640, dtype=np.float32))), final=True)
                        finally:
                            processor.close()
                        before_batch = time.perf_counter()
                        batch = backend.transcribe_batch(batch_audio)
                        row["batch_decode_seconds"] = time.perf_counter() - before_batch
                        if "text" in entry:
                            row["batch_errors"], _ = word_errors(entry["text"], batch)
                    if not text.strip() and entry.get("text", "speech"):
                        row["error"] = "Speech returned an empty transcript"
                except Exception as exc:
                    row["error"] = type(exc).__name__
                    backend.preload()
                row.update(session.metrics)
                report["rows"].append(row)
                print(json.dumps(row), flush=True)
        report["summary"] = []
        for noise in modes:
            rows = [row for row in report["rows"] if row["noise_suppression"] == noise]
            latencies = [row["release_to_final_seconds"] for row in rows if "release_to_final_seconds" in row]
            summary = {"noise_suppression": noise, "clips": len(rows), "failures": sum("error" in row for row in rows),
                       "median_release_to_final_seconds": statistics.median(latencies) if latencies else None,
                       "max_release_to_final_seconds": max(latencies, default=None),
                       "errors": sum(row.get("errors", 0) for row in rows),
                       "reference_words": sum(row.get("reference_words", 0) for row in rows)}
            if args.compare_batch:
                summary["batch_errors"] = sum(row.get("batch_errors", 0) for row in rows)
            report["summary"].append(summary)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report["summary"]), flush=True)
    finally:
        backend.close()
    return 1 if any("error" in row for row in report["rows"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
