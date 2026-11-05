"""Replay bundled public speech through installed catalog models, one at a time.

No microphone, clipboard, downloads, or changes to the running app. This checks
format/adapter compatibility, not broad recognition accuracy or live latency.
"""
from pathlib import Path
import argparse
import json
import os
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', action='append')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/model-library-replay.json')
    args = parser.parse_args()
    os.environ['HF_HUB_OFFLINE'] = '1'
    import numpy as np
    from voiceprompt.model_library import ModelLibrary
    from voiceprompt.backend_process import ManagedTranscriber
    from voiceprompt.config import Settings
    from voiceprompt.session import DictationSession, ReplayRecorder
    library = ModelLibrary(ROOT / 'build/model-library-smoke')
    with wave.open(str(ROOT / 'voiceprompt/assets/nemotron-warmup.wav'), 'rb') as source:
        assert source.getframerate() == 16000 and source.getsampwidth() == 2
        audio = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').astype(np.float32) / 32768
    chunks = [(audio[start:start + 1600], 16000) for start in range(0, len(audio), 1600)]
    report = []
    for model in library.catalog['models']:
        if args.model and model['id'] not in args.model: continue
        row = {'id': model['id']}
        backend = None
        try:
            settings = Settings(selected_model_id=model['id'], backend=model['engine'], nemotron_device='cpu')
            settings = library.runtime_settings(settings, verify=True)
            backend = ManagedTranscriber(settings)
            started = time.perf_counter(); backend.preload()
            row['preparation_seconds'] = time.perf_counter() - started
            session = DictationSession(1)
            text, duration = session.run(ReplayRecorder(chunks, session), backend, hotwords='', noise_suppression=False)
            row.update(passed=bool(text.strip()), output_words=len(text.split()), duration_seconds=duration, metrics=session.metrics)
            session.audio_queue.clear()
        except Exception as exc:
            row.update(passed=False, error=f'{type(exc).__name__}: {exc}')
        finally:
            if backend is not None: backend.close()
        report.append(row)
        print(json.dumps({key: value for key, value in row.items() if key != 'metrics'}), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'rows': report, 'limits': __doc__}, indent=2), encoding='utf-8')
    if not report or any(not row['passed'] for row in report): raise SystemExit(1)


if __name__ == '__main__': main()
