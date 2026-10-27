"""Frozen sidecar entry: dispatch workers before importing the controller."""
import sys


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--speech-worker':
        from voiceprompt.backend_process import run_worker
        run_worker(int(sys.argv[2]))
    elif len(sys.argv) == 4 and sys.argv[1] == '--nemotron-worker':
        from voiceprompt.nemotron_process import run_worker
        run_worker(int(sys.argv[2]), sys.argv[3])
    elif len(sys.argv) in (3, 4) and sys.argv[1] == '--smoke-test':
        from voiceprompt.smoke import run
        try:
            run(sys.argv[2], hold_for_uninstall='--hold-for-uninstall' in sys.argv, headless=True)
        except Exception as exc:
            import json
            from pathlib import Path
            Path(sys.argv[2]).write_text(json.dumps({'error': type(exc).__name__}), encoding='utf-8')
            raise
    else:
        from voiceprompt.desktop_sidecar import main as sidecar_main
        return sidecar_main()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
