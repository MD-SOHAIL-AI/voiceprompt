"""Render the Qt interface with disposable sample data, without hooks or a mic."""
import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("evaluation/desktop"))
    parser.add_argument("--scale", default="1")
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()
    if not args.interactive:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_SCALE_FACTOR"] = args.scale
    from voiceprompt.desktop import DesktopHost, PAGES
    from desktop_helpers import make_controller
    import queue
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        controller = make_controller(directory)
        controller.planner.save_task("Practice graph algorithms", "Revisit shortest paths")
        controller.planner.save_task("Read for twenty minutes")
        controller.planner.start_timer("Practice graph algorithms", 5400)
        controller.latest_text = "I would like to turn this idea into a useful app. Let’s start with reliable voice typing, then make the rest easy to use."
        host = DesktopHost(controller, type("Adapter", (), {"events": queue.SimpleQueue()})())
        if args.interactive:
            host.window.setWindowTitle("VoicePrompt Preview — disposable sample data")
            controller.quit.side_effect = host.stop
            host.run()
            controller.planner.close()
            return
        host.window.resize(1120, 790)
        host.window.show()
        for page in PAGES:
            host.window.show_page(page)
            host.window.refresh(force=True)
            host.app.processEvents()
            host.window.grab().save(str(args.output / f"{page.replace(' ', '-').lower()}-{args.scale}.png"))
        controller.settings.onboarding_completed = False
        host.window.show_page("Dictation")
        host.window.refresh(force=True)
        host.app.processEvents()
        host.window.grab().save(str(args.output / f"onboarding-{args.scale}.png"))
        host.stop()
        controller.planner.close()


if __name__ == "__main__":
    main()
