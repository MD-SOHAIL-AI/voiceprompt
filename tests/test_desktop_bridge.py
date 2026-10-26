import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from voiceprompt.config import Settings
from voiceprompt.desktop_protocol import MAX_MESSAGE_BYTES, Writer, read_messages
from voiceprompt.desktop_sidecar import DesktopService, validate_settings
from voiceprompt.history import TranscriptionHistory
from voiceprompt.planner import PlannerService
from voiceprompt.recorder import PushToTalkRecorder


class DesktopBridgeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.clock = SimpleNamespace(wall=1790000000.0, mono=1000.0)
        self.planner = self.make_planner()
        self.planner.update_preferences(daily_summary=False)
        self.addCleanup(lambda: self.planner.close())
        self.app = SimpleNamespace(planner=self.planner, _planner_error='', _control=threading.RLock(),
            history=TranscriptionHistory(self.root / 'history.json'), settings=Settings(),
            pill=SimpleNamespace(on_navigation=None), latest_text='')
        self.service = DesktopService(self.app, Writer(io.BytesIO()))

    def make_planner(self):
        return PlannerService(self.root / 'planner.sqlite3', now=lambda: self.clock.wall, monotonic=lambda: self.clock.mono, network_enabled=False)

    def advance(self, seconds):
        self.clock.wall += seconds
        self.clock.mono += seconds
        self.planner.tick()

    def test_oversized_command_is_drained_and_next_command_survives(self):
        command = {'id': 2, 'version': 1, 'method': 'runtime', 'params': {}}
        frames = list(read_messages(io.BytesIO(b'x' * (MAX_MESSAGE_BYTES + 2) + b'\n' + json.dumps(command).encode() + b'\n')))
        self.assertIsNotNone(frames[0][1])
        self.assertEqual(frames[1], (command, None))

    def test_invalid_protocol_inputs_do_not_become_commands(self):
        for value in [[], {'id': True, 'version': 1, 'method': 'runtime'}, {'id': 1, 'version': True, 'method': 'runtime'}, {'id': 1, 'version': 9, 'method': 'runtime'}, {'id': 1, 'version': 1, 'method': 'runtime', 'params': []}]:
            message, error = next(read_messages(io.BytesIO(json.dumps(value).encode() + b'\n')))
            self.assertIsNone(message)
            self.assertTrue(error)

    def test_concurrent_events_are_parseable_and_ordered(self):
        buffer = io.BytesIO()
        writer = Writer(buffer)
        threads = [threading.Thread(target=lambda: [writer.event('meter', {'values': [0.1]}) for _ in range(25)]) for _ in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        messages = [json.loads(line) for line in buffer.getvalue().splitlines()]
        self.assertEqual([m['sequence'] for m in messages], list(range(1, 101)))

    def test_stale_timer_cannot_cancel_new_session(self):
        self.planner.start_timer('First', 60)
        old = self.planner.snapshot()['timer']['session']
        self.planner.start_timer('Second', 120, replace=True)
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.service.dispatch('planner.timer.action', {'session': old, 'action': 'cancel'})
        self.assertEqual(self.planner.snapshot()['timer']['title'], 'Second')
        self.assertEqual(self.planner.snapshot()['timer']['status'], 'running')

    def test_snooze_removes_badge_and_old_revision_is_rejected(self):
        self.planner.save_task('Read', due=self.clock.wall)
        self.planner.tick()
        item = self.service.planner_snapshot()['notifications'][0]
        self.service.dispatch('planner.notification.act', {'id': item['id'], 'revision': 0, 'snooze': True})
        self.assertEqual(self.service.planner_snapshot()['pendingCount'], 0)
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.service.dispatch('planner.notification.act', {'id': item['id'], 'revision': 0, 'snooze': False})
        self.advance(300)
        self.assertEqual(self.service.planner_snapshot()['pendingCount'], 1)

    def test_presenting_is_not_acknowledging_or_completing(self):
        task = self.planner.save_task('Read', due=self.clock.wall)
        self.planner.tick()
        item = self.service.planner_snapshot()['notifications'][0]
        self.service.dispatch('planner.notifications.presented', {'items': [{'id': item['id'], 'revision': 0}]})
        self.assertEqual(self.service.planner_snapshot()['pendingCount'], 1)
        self.assertFalse(self.planner.store.get('task', task)['done'])

    def test_delivery_budget_survives_restart(self):
        self.planner.save_task('Read', due=self.clock.wall)
        self.planner.tick()
        self.assertTrue(self.planner.claim_reminder_sound())
        self.planner.close()
        self.planner = self.make_planner()
        self.advance(60)
        self.assertFalse(self.planner.claim_reminder_sound())

    def test_alarm_repeats_are_bounded_and_edit_preserves_disabled(self):
        alarm = self.planner.save_alarm('Break', self.clock.wall + 10)
        self.planner.toggle_alarm(alarm)
        self.planner.save_alarm('Renamed', self.clock.wall + 20, item_id=alarm)
        self.assertFalse(self.planner.store.get('alarm', alarm)['enabled'])
        self.planner.toggle_alarm(alarm)
        self.advance(20)
        self.assertTrue(self.planner.claim_reminder_sound())
        self.assertFalse(self.planner.claim_reminder_sound())
        for _ in range(2):
            self.advance(10)
            self.assertTrue(self.planner.claim_reminder_sound())
        self.advance(10)
        self.assertFalse(self.planner.claim_reminder_sound())

    def test_contest_start_replaces_advance_and_survives_next_tick(self):
        contest = {'id': 'codeforces:123', 'platform': 'codeforces', 'name': 'Round', 'url': 'https://codeforces.com/contest/123', 'start': self.clock.wall + 60, 'end': self.clock.wall + 3600, 'source': 'codeforces', 'muted': False}
        with self.planner.store.transaction(): self.planner.store.put('contest', contest)
        self.planner.tick()
        self.assertEqual(self.service.planner_snapshot()['notifications'][0]['kind'], 'contest')
        self.advance(60)
        self.planner.tick()
        pending = self.service.planner_snapshot()['notifications']
        self.assertEqual(len(pending), 1)
        self.assertTrue(pending[0]['id'].endswith(':started'))
        self.advance(3600)
        self.assertEqual(self.service.planner_snapshot()['pendingCount'], 0)

    def test_corrupt_optional_planner_is_isolated(self):
        with patch.object(self.planner, 'snapshot', side_effect=ValueError('bad data')):
            self.assertIsNone(self.service.planner_snapshot())
        self.assertIn('kept', self.app._planner_error)

    def test_legacy_history_ids_survive_reload_and_delete(self):
        self.app.history.path.write_text(json.dumps([{'text': 'one', 'created_at': '2026-10-26'}, {'text': 'two', 'created_at': '2026-10-25'}]))
        first, second = self.app.history.load()
        self.assertEqual(first.id, self.app.history.load()[0].id)
        self.service.dispatch('history.delete', {'id': first.id})
        self.assertEqual([item.text for item in self.app.history.load()], ['two'])
        self.assertEqual(self.app.history.load()[0].id, second.id)

    def test_settings_reject_invalid_types_and_nan(self):
        for update in ({'sound_feedback': 'yes'}, {'max_history': -1}, {'cleanup_timeout_seconds': float('nan')}, {'api_key': 'secret'}, {'replacements': {'': 'value'}}):
            with self.assertRaises(ValueError): validate_settings(Settings(), update)

    def test_meter_leaves_recognition_frames_intact_and_decays(self):
        recorder = PushToTalkRecorder()
        recorder._capturing = True
        delivered = []
        recorder.on_audio_chunk = lambda chunk, rate: delivered.append(len(chunk))
        status = SimpleNamespace(input_overflow=False)
        recorder._on_audio(np.full((1024, 1), .1, dtype=np.float32), 1024, None, status)
        self.assertGreater(max(recorder.envelope()), .5)
        for _ in range(25): recorder._on_audio(np.zeros((1024, 1), dtype=np.float32), 1024, None, status)
        self.assertLess(recorder.envelope()[-1], .01)
        self.assertEqual(sum(delivered), 26 * 1024)
        recorder._capturing = False
        self.assertEqual(recorder.envelope(), [0.0] * 32)
