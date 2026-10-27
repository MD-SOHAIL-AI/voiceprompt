"""Disposable fixtures for the real packaged bridge; no personal data or keys."""
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voiceprompt.config import Settings
from voiceprompt.planner import PlannerService

path = Path(sys.argv[1]).resolve()
path.mkdir(parents=True, exist_ok=True)
if (path / 'config.json').exists():
    raise SystemExit('Use a new, empty acceptance profile directory.')
settings = Settings(onboarding_completed=True, preload_model=False, sound_feedback=False, max_history=10)
(path / 'config.json').write_text(json.dumps(asdict(settings)), encoding='utf-8')
(path / 'history.json').write_text(json.dumps([{'id': 'acceptance-transcript', 'text': 'Acceptance transcript. This is synthetic verification data.', 'created_at': datetime.now(timezone.utc).isoformat(), 'duration_seconds': 3, 'source': 'fixture'}]), encoding='utf-8')
planner = PlannerService(path / 'planner.sqlite3', network_enabled=False)
planner.update_preferences(daily_summary=False, reminder_sound=False)
planner.save_task('Acceptance task', 'Synthetic task for native verification')
planner.save_alarm('Acceptance fixture alarm', time.time() + 3600)
with planner.store.transaction():
    planner.store.put('contest', {'id': 'acceptance-contest', 'platform': 'codeforces', 'name': 'Acceptance Codeforces round', 'url': 'https://codeforces.com/contests', 'start': time.time() + 3600, 'end': time.time() + 10800, 'source': 'codeforces', 'muted': False})
planner.close()
print('Created isolated verification data.')
