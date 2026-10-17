"""Local recording/evaluation CLI. Never uploads audio or changes app settings."""
from __future__ import annotations

import argparse
import ctypes
import gc
import json
import re
import statistics
import subprocess
import sys
import threading
import time
import wave
from dataclasses import replace
from pathlib import Path

import numpy as np

from voiceprompt.config import Settings
from voiceprompt.main import VoicePromptApp
from voiceprompt.recorder import PushToTalkRecorder, RecorderConfig, Recording
from voiceprompt.replacements import apply_replacements
from voiceprompt.session import DictationSession
from voiceprompt.transcriber import create_transcriber


CANDIDATES = {
    "baseline": Settings(beam_size=3),
    "whisper-fast": Settings(beam_size=1),
    "whisper-distil": Settings(model="Systran/faster-distil-whisper-small.en", beam_size=1),
    "moonshine-small": Settings(backend="moonshine", streaming_model="small"),
    "moonshine-tiny": Settings(backend="moonshine", streaming_model="tiny"),
    "parakeet": Settings(backend="parakeet"),
    "nemotron": Settings(backend="nemotron", nemotron_device="vulkan"),
}
PROMPTS = [
    "Please send the updated project report before five tomorrow afternoon.",
    "OpenRouter and Claude Code help me work on embedded systems.",
    "The meeting starts at nine thirty and should last forty five minutes.",
    "Set the timeout to four seconds and retry the request three times.",
    "I want to improve recognition accuracy without increasing the response delay.",
    "My laptop has eight gigabytes of memory and an AMD Ryzen processor.",
    "ChatGPT should preserve the numbers and names in this sentence.",
    "Create a new branch and run the tests before saving the changes.",
    "The traffic outside is loud but I still need to dictate clearly.",
    "Yesterday I reviewed the application and found a problem with the microphone. Today I want to test the recording again, compare the results, and decide which speech model works best for my normal work.",
]


def words(text: str) -> list[str]:
    return re.findall(r"\w+(?:['’]\w+)?", text.casefold())


def word_errors(reference: str, hypothesis: str) -> tuple[int, int]:
    expected, actual = words(reference), words(hypothesis)
    previous = list(range(len(actual) + 1))
    for i, word in enumerate(expected, 1):
        current = [i]
        for j, other in enumerate(actual, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (word != other)))
        previous = current
    return previous[-1], len(expected)


def percentile(values: list[float], fraction: float) -> float:
    return float(np.quantile(values, fraction)) if values else 0.0


def process_peak_mb(pid: int | None = None) -> float:
    if sys.platform != "win32":
        return 0.0

    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
            )
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32")
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    psapi = ctypes.WinDLL("psapi")
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    handle = kernel.OpenProcess(0x1000, False, pid) if pid is not None else kernel.GetCurrentProcess()
    if not handle:
        raise ctypes.WinError()
    try:
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            raise ctypes.WinError()
    finally:
        if pid is not None:
            kernel.CloseHandle(handle)
    return counters.PeakWorkingSetSize / 1024**2


class ReplayRecorder:
    """Feed WAV data at microphone pace, including a captured release tail."""

    def __init__(self, audio: np.ndarray, sample_rate: int, session: DictationSession) -> None:
        self.audio = audio
        self.sample_rate = sample_rate
        self.session = session
        self.config = RecorderConfig(min_seconds=0)
        self.is_recording = False
        self.on_audio_chunk = None
        self.input_overflows = 0
        self.callback_error = ""
        self.capture_failed = False
        self.capture_open_seconds = 0.0
        self.input_latency_seconds = 0.0
        self.host_api = "WAV replay"
        self._stop = threading.Event()
        self._thread = None

    def prepare(self) -> None:
        pass

    def start(self) -> None:
        self.is_recording = True
        self._thread = threading.Thread(target=self._feed, daemon=True)
        self._thread.start()

    def _feed(self) -> None:
        started = time.perf_counter()
        size = max(1, int(self.sample_rate * 0.02))
        for offset in range(0, len(self.audio), size):
            if self._stop.is_set():
                return
            self.on_audio_chunk(self.audio[offset:offset + size], self.sample_rate)
            if self._stop.wait(max(0, started + min(offset + size, len(self.audio)) / self.sample_rate - time.perf_counter())):
                return
        self.session.request_release()
        for _ in range(9):
            if self._stop.is_set():
                return
            self.on_audio_chunk(np.zeros(size, dtype=np.float32), self.sample_rate)
            if self._stop.wait(0.02):
                return

    def stop(self, *, grace: bool = True, released_at=None) -> Recording:
        if grace and self._thread:
            self._thread.join(timeout=1)
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        self.is_recording = False
        return Recording(self.audio, self.sample_rate, len(self.audio) / self.sample_rate)


def load_manifest(path: Path) -> list[dict]:
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("condition") not in {"clean", "fan", "traffic", "noise", "stress"}:
            raise ValueError("Each entry needs condition clean, fan, traffic, noise, or stress.")
        entry["audio"] = str((path.parent / entry["audio"]).resolve())
        if not Path(entry["audio"]).is_file():
            raise ValueError(f"Missing WAV: {entry['audio']}")
        if not isinstance(entry.get("text"), str):
            raise ValueError("Every manifest entry needs a text reference, empty for noise-only.")
        entries.append(entry)
    if not entries:
        raise ValueError("The evaluation manifest is empty.")
    return entries


def summarize(rows: list[dict]) -> dict:
    summary = {}
    for condition in ("clean", "fan", "traffic", "noise", "stress"):
        selected = [r for r in rows if r["condition"] == condition]
        if not selected:
            continue
        expected_words = sum(r["reference_words"] for r in selected)
        summary[condition] = {
            "clips": len(selected), "errors": sum(r["errors"] for r in selected),
            "reference_words": expected_words,
            "wer": sum(r["errors"] for r in selected) / expected_words if expected_words else None,
            "hallucinated_clips": sum(bool(r["hypothesis"].strip()) for r in selected) if condition == "noise" else 0,
            "failed_clips": sum("error" in r for r in selected),
        }
    # Silence-only clips must not lower the latency reported for dictation.
    latencies = [
        r["release_to_final_seconds"] + 0.14 for r in rows
        if r["reference_words"] > 0 and "release_to_final_seconds" in r
    ]
    summary.update(
        estimated_median_release_to_paste_seconds=statistics.median(latencies) if latencies else None,
        estimated_p95_release_to_paste_seconds=percentile(latencies, 0.95) if latencies else None,
        peak_process_mb=process_peak_mb(),
        max_queue_seconds=max((r.get("queue_peak_seconds", 0) for r in rows), default=0),
        max_processing_rtf=max((r.get("decoding_seconds", 0) / max(r["duration_seconds"], 0.01) for r in rows), default=0),
        term_hits=sum(r.get("term_hits", 0) for r in rows),
        term_count=sum(r.get("term_count", 0) for r in rows),
    )
    return summary


def evaluate_candidate(manifest: Path, candidate: str, noise: bool, threads: int) -> dict:
    from faster_whisper.audio import decode_audio

    settings = replace(CANDIDATES[candidate], noise_suppression=noise, cpu_threads=threads)
    backend = create_transcriber(settings)
    rows = []
    started = time.perf_counter()
    try:
        backend.preload()
        if backend.fallback_reason:
            raise RuntimeError(backend.fallback_reason)
        warmup = time.perf_counter() - started
        for index, entry in enumerate(load_manifest(manifest)):
            audio = decode_audio(entry["audio"], sampling_rate=48000)
            session = DictationSession(index + 1)
            recorder = ReplayRecorder(audio, 48000, session)
            row = {"audio": entry["audio"], "condition": entry["condition"], "reference": entry["text"], "duration_seconds": len(audio) / 48000}
            try:
                text, _ = session.run(recorder, backend, hotwords=VoicePromptApp._hotwords(settings), noise_suppression=noise)
                text = apply_replacements(text, settings.replacements)
                row["hypothesis"] = text
            except Exception as exc:
                row["hypothesis"] = ""
                row["error"] = f"{type(exc).__name__}: {exc}"
            row.update(session.metrics)
            row["errors"], row["reference_words"] = word_errors(entry["text"], row["hypothesis"])
            terms = entry.get("keyterms", [])
            normalized = " " + " ".join(words(row["hypothesis"])) + " "
            row["term_hits"] = sum(" " + " ".join(words(term)) + " " in normalized for term in terms)
            row["term_count"] = len(terms)
            rows.append(row)
        summary = summarize(rows)
        if candidate == "nemotron":
            summary["peak_app_process_mb"] = summary["peak_process_mb"]
            summary["peak_native_worker_mb"] = process_peak_mb(backend.worker_pid)
            summary["peak_process_mb"] += summary["peak_native_worker_mb"]
            summary["memory_scope"] = "Sum of app/worker working-set peaks; graphics allocations excluded."
        return {"candidate": candidate, "noise_suppression": noise, "cpu_threads": "runtime default" if candidate == "nemotron" else threads, "warmup_seconds": warmup, "rows": rows, "summary": summary}
    finally:
        backend.close()
        gc.collect()


def select_candidate(results: list[dict]) -> dict:
    baseline = next((r for r in results if r["candidate"] == "baseline" and not r.get("noise_suppression") and "summary" in r), None)
    if baseline is None:
        return {"selected": "baseline", "reason": "Baseline could not be evaluated; settings are unchanged."}
    baseline_summary = baseline["summary"]
    if any(k not in baseline_summary for k in ("clean", "fan", "traffic", "noise", "stress")) or sum(baseline_summary[k]["clips"] for k in ("clean", "fan", "traffic")) < 30:
        return {"selected": "baseline", "reason": "Need 30 speech clips across clean/fan/traffic, noise-only clips, and a 60-second stress clip before promotion."}
    if any("error" in r for r in baseline["rows"]):
        return {"selected": "baseline", "reason": "Baseline has failed clips; fix evaluation before selecting a model."}
    eligible = []
    for result in results:
        if result["candidate"] == "baseline" or "summary" not in result:
            continue
        s = result["summary"]
        if any("error" in r for r in result["rows"]):
            continue
        noisy_words = sum(s[k]["reference_words"] for k in ("fan", "traffic"))
        base_noisy_words = sum(baseline_summary[k]["reference_words"] for k in ("fan", "traffic"))
        noisy_wer = sum(s[k]["errors"] for k in ("fan", "traffic")) / max(noisy_words, 1)
        base_noisy_wer = sum(baseline_summary[k]["errors"] for k in ("fan", "traffic")) / max(base_noisy_words, 1)
        stress_rows = [r for r in result["rows"] if r["condition"] == "stress"]
        if not any(r["duration_seconds"] >= 60 for r in stress_rows):
            continue
        if (
            s["estimated_median_release_to_paste_seconds"] <= baseline_summary["estimated_median_release_to_paste_seconds"] * 0.5
            and noisy_wer <= base_noisy_wer * 0.8
            and s["clean"]["wer"] <= baseline_summary["clean"]["wer"] + 0.01
            and s["noise"]["hallucinated_clips"] == 0
            and s["max_processing_rtf"] < 1.0 and s["peak_process_mb"] <= 1024
        ):
            eligible.append((noisy_wer, s["estimated_p95_release_to_paste_seconds"], s["peak_process_mb"], result))
    if not eligible:
        return {"selected": "baseline", "reason": "No candidate meets all latency, accuracy, noise, streaming, and memory gates. Settings are unchanged."}
    best = min(eligible, key=lambda row: row[:3])[3]
    return {"selected": best["candidate"], "noise_suppression": best["noise_suppression"], "cpu_threads": best["cpu_threads"], "reason": "Replay gates passed. Confirm actual paste timings in performance.jsonl before changing Settings."}


def record_suite(directory: Path, seconds: float, microphone: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "manifest.jsonl"
    recorder = PushToTalkRecorder(RecorderConfig(sample_rate=48000, microphone=microphone))
    recorder.prepare()
    try:
        for condition in ("clean", "fan", "traffic", "noise", "stress"):
            print(f"\nCondition: {condition}. Use actual noise at your normal speaking distance.")
            prompts = PROMPTS if condition in {"clean", "fan", "traffic"} else [""] if condition == "noise" else [" ".join(PROMPTS)]
            for index, prompt in enumerate(prompts, 1):
                filename = f"{condition}-{index:02}.wav"
                if (directory / filename).exists():
                    continue
                duration = 65 if condition == "stress" else 25 if index == 10 else seconds
                print(f"\nRead aloud ({duration:g} seconds): {prompt or '[Remain silent; record background noise only]'}")
                input("Press Enter when ready; recording begins immediately. ")
                recorder.start()
                time.sleep(duration)
                if recorder.capture_failed:
                    raise RuntimeError("The microphone stopped during recording. Reconnect it and rerun to resume.")
                result = recorder.stop()
                if result is None or recorder.input_overflows or recorder.callback_error:
                    raise RuntimeError("Recording failed or dropped frames. Rerun to resume.")
                with wave.open(str(directory / filename), "wb") as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(result.sample_rate)
                    output.writeframes((np.clip(result.audio, -1, 1) * 32767).astype("<i2").tobytes())
                actual = input("Enter corrected reference if you spoke different words, or Enter to keep the prompt: ").strip() or prompt
                entry = {"audio": filename, "text": actual, "condition": condition}
                normalized = " " + " ".join(words(actual)) + " "
                entry["keyterms"] = [
                    term for term in ("OpenRouter", "Claude Code", "embedded systems", "ChatGPT")
                    if " " + " ".join(words(term)) + " " in normalized
                ]
                with manifest.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(entry) + "\n")
        print(f"\nSaved locally: {manifest}")
    finally:
        recorder.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record", help="Record a guided local evaluation set")
    record.add_argument("--directory", type=Path, default=Path("evaluation/voice"))
    record.add_argument("--seconds", type=float, default=10)
    record.add_argument("--microphone", default="")
    run = commands.add_parser("run", help="Compare identical WAVs in isolated processes")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--output", type=Path, default=Path("evaluation/results.json"))
    run.add_argument("--candidates", nargs="+", choices=list(CANDIDATES), default=list(CANDIDATES))
    run.add_argument("--noise-comparison", action="store_true")
    run.add_argument("--thread-sweep", action="store_true")
    child = commands.add_parser("candidate", help="Internal worker used by run")
    child.add_argument("--manifest", type=Path, required=True)
    child.add_argument("--name", choices=list(CANDIDATES), required=True)
    child.add_argument("--noise", action="store_true")
    child.add_argument("--threads", type=int, default=4)
    child.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "record":
        if not 1 <= args.seconds <= 30:
            parser.error("--seconds must be between 1 and 30")
        record_suite(args.directory, args.seconds, args.microphone)
        return
    load_manifest(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.command == "candidate":
        try:
            result = evaluate_candidate(args.manifest, args.name, args.noise, args.threads)
        except Exception as exc:
            result = {"candidate": args.name, "noise_suppression": args.noise, "cpu_threads": args.threads, "error": f"{type(exc).__name__}: {exc}"}
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return
    results = []
    for candidate in args.candidates:
        for noise in ([False, True] if args.noise_comparison and candidate != "baseline" else [False]):
            for threads in ([2, 4, 6] if args.thread_sweep and (candidate.startswith("whisper") or candidate == "parakeet") else [4]):
                print(f"Evaluating {candidate}, suppression={noise}, threads={threads}", flush=True)
                output = args.output.with_name(f"{args.output.stem}-{candidate}-{'noise' if noise else 'raw'}-{threads}.json")
                command = [sys.executable, "-m", "voiceprompt.evaluate", "candidate", "--manifest", str(args.manifest.resolve()), "--name", candidate, "--threads", str(threads), "--output", str(output.resolve())]
                if noise:
                    command.append("--noise")
                subprocess.run(command, check=True)
                results.append(json.loads(output.read_text(encoding="utf-8")))
                report = {"measurement": "Real-time WAV replay; paste overhead estimated at 140 ms, not measured GUI insertion.", "results": results, "selection": select_candidate(results)}
                args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["selection"], indent=2))


if __name__ == "__main__":
    main()
