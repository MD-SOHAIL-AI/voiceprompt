from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from voiceprompt.planner import PlannerService, local_timestamp, next_alarm
from voiceprompt.contests import ContestFetchError


class Clock:
    def __init__(self):
        self.wall = datetime(2026, 10, 15, 3, 0, tzinfo=timezone.utc).timestamp()
        self.mono = 100.0

    def advance(self, seconds):
        self.wall += seconds
        self.mono += seconds


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.clock = Clock()
        self.path = Path(self.directory.name) / "planner.sqlite3"
        self.service = self.make_service()
        self.addCleanup(lambda: self.service.close())

    def make_service(self):
        return PlannerService(self.path, now=lambda: self.clock.wall, monotonic=lambda: self.clock.mono, credentials=MagicMock())

    def notifications(self):
        return [n for n in self.service.snapshot()["notifications"] if not n["dismissed"]]

    def put_contest(self, **overrides):
        contest = {"id": "clist:42", "name": "Weekly Contest", "platform": "leetcode", "source": "clist",
                   "url": "https://leetcode.com/contest/weekly-contest-42/", "start": self.clock.wall + 600,
                   "end": self.clock.wall + 6000, "muted": False, **overrides}
        with self.service.store.transaction():
            self.service.store.put("contest", contest)
        return contest

    def test_arbitrary_durations_and_exactly_one_completion(self):
        for minutes in (20, 25, 30, 45, 90, 120):
            self.service.start_timer("Any activity", minutes * 60)
            self.clock.advance(minutes * 60 - 1)
            self.service.tick()
            self.assertEqual(self.service.snapshot()["timer"]["status"], "running")
            self.clock.advance(1)
            self.service.tick()
            self.service.tick()
            self.assertEqual(self.service.snapshot()["timer"]["status"], "completed")
            self.assertEqual(len(self.notifications()), 1)

    def test_pause_resume_and_explicit_replacement(self):
        self.service.start_timer("DSA", 100)
        with self.assertRaisesRegex(ValueError, "already active"):
            self.service.start_timer("Jogging", 100)
        self.clock.advance(30)
        self.service.timer_action("pause")
        self.clock.advance(500)
        self.service.tick()
        self.assertEqual(self.service.snapshot()["timer"]["remaining"], 70)
        self.service.timer_action("resume")
        self.clock.advance(70)
        self.service.tick()
        self.assertEqual(len(self.notifications()), 1)
        self.service.start_timer("Jogging", 120, replace=True)
        self.assertEqual(self.service.snapshot()["timer"]["title"], "Jogging")

    def test_cancel_and_restart_remove_pending_notifications(self):
        self.service.start_timer("Read", 60)
        self.clock.advance(60)
        self.service.tick()
        self.service.timer_action("restart")
        self.assertEqual(self.notifications(), [])
        self.service.timer_action("cancel")
        self.clock.advance(120)
        self.service.tick()
        self.assertEqual(self.notifications(), [])

    def test_timer_survives_restart_and_clock_adjustment(self):
        self.service.start_timer("Learn", 100)
        self.clock.advance(20)
        self.clock.wall += 3600
        self.service.tick()
        self.assertEqual(self.service.snapshot()["timer"]["remaining"], 80)
        self.service.close()
        self.clock.advance(90)
        self.service = self.make_service()
        self.service.tick()
        self.assertEqual(len(self.notifications()), 1)
        self.service.close()
        self.service = self.make_service()
        self.service.tick()
        self.assertEqual(len(self.notifications()), 1)

    def test_pomodoro_cycles_finish_after_final_long_break(self):
        self.service.start_timer("Study", 10, mode="pomodoro", short_break=5, long_break=15, rounds=2)
        for seconds, expected in ((10, "short_break"), (5, "work"), (10, "long_break"), (15, "finished")):
            self.clock.advance(seconds)
            self.service.tick()
            self.assertEqual(self.service.snapshot()["timer"]["phase"], expected)
        self.assertEqual(self.service.snapshot()["timer"]["status"], "completed")

    def test_sleep_pauses_overdue_pomodoro_without_counting_skipped_rounds(self):
        self.service.start_timer("Study", 10, mode="pomodoro", short_break=5, rounds=4)
        self.clock.advance(3600)
        self.service.tick()
        timer = self.service.snapshot()["timer"]
        self.assertEqual((timer["status"], timer["phase"], timer["completed"]), ("paused", "short_break", 1))
        self.service.tick()
        self.assertEqual(len(self.notifications()), 1)

    def test_recovered_future_pomodoro_keeps_automatic_transitions(self):
        self.service.start_timer("Study", 10, mode="pomodoro")
        self.service.close()
        self.service = self.make_service()
        self.service.tick()
        self.clock.advance(10)
        self.service.tick()
        self.assertEqual(self.service.snapshot()["timer"]["status"], "running")

    def test_invalid_timer_values_are_rejected(self):
        for value in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.service.start_timer("Study", value)

    def test_task_reminder_completion_and_snooze(self):
        task = self.service.save_task("Read", "Chapter 1", self.clock.wall + 60)
        self.clock.advance(60)
        self.service.tick()
        item = self.notifications()[0]
        self.service.acknowledge(item["id"], snooze=True)
        self.assertEqual(self.notifications()[0]["due"], self.clock.wall + 300)
        self.service.complete_task(task)
        self.service.tick()
        self.assertEqual(self.notifications(), [])

    def test_acknowledged_old_task_does_not_notify_again_after_pruning(self):
        self.service.save_task("Read", due=self.clock.wall)
        self.service.tick()
        self.service.acknowledge(self.notifications()[0]["id"])
        self.clock.advance(31 * 86400)
        self.service.tick()
        self.service.tick()
        self.assertEqual(self.notifications(), [])

    def test_deleting_task_cancels_snoozed_reminder(self):
        task = self.service.save_task("Read", due=self.clock.wall)
        self.service.tick()
        self.service.acknowledge(self.notifications()[0]["id"], True)
        self.service.delete("task", task)
        self.clock.advance(300)
        self.service.tick()
        self.assertEqual(self.notifications(), [])

    def test_one_time_alarm_fires_once_and_recurring_alarm_skips_missed_days(self):
        self.service.save_alarm("One time", self.clock.wall + 60)
        repeating = self.service.save_alarm("Every day", self.clock.wall + 60, list(range(7)))
        self.clock.advance(3 * 86400 + 60)
        self.service.tick()
        self.service.tick()
        self.assertEqual(len(self.notifications()), 2)
        self.assertGreater(self.service.store.get("alarm", repeating)["due"], self.clock.wall)

    def test_disabled_alarm_cancels_its_pending_notification(self):
        alarm = self.service.save_alarm("Daily", self.clock.wall + 60, list(range(7)))
        self.clock.advance(60)
        self.service.tick()
        self.service.toggle_alarm(alarm)
        self.assertEqual(self.notifications(), [])

    def test_contest_lead_summary_and_restart_deduplication(self):
        self.put_contest(start=self.clock.wall + 1800, end=self.clock.wall + 9000)
        self.clock.advance(1800)  # 9 AM IST, contest just started: one contest alert, no stale summary.
        self.service.tick()
        self.assertEqual(len(self.notifications()), 1)
        self.put_contest(id="clist:43", start=self.clock.wall + 7200, end=self.clock.wall + 9000)
        self.service.tick()
        self.assertEqual(len(self.notifications()), 2)
        self.service.close()
        self.service = self.make_service()
        self.service.tick()
        self.assertEqual(len(self.notifications()), 2)

    def test_muting_and_disabling_platform_cancel_pending_alerts(self):
        contest = self.put_contest()
        self.service.tick()
        self.assertEqual(len(self.notifications()), 1)
        self.service.mute_contest(contest["id"])
        self.assertEqual(self.notifications(), [])
        self.service.mute_contest(contest["id"])
        self.service.update_preferences(platforms=["codeforces"])
        self.service.tick()
        self.assertEqual(self.notifications(), [])

    def test_complete_refresh_deduplicates_reschedules_and_reconciles_missing_contests(self):
        old = self.put_contest()
        self.service.tick()
        new = {**old, "start": self.clock.wall + 7200}
        with self.service.store.transaction():
            self.service._merge_contests("clist", [new, new])
        self.assertEqual(len(self.service.snapshot()["contests"]), 1)
        self.assertEqual(self.notifications(), [])
        with self.service.store.transaction():
            self.service._merge_contests("clist", [])
        self.assertEqual(self.service.snapshot()["contests"], [])

    def test_failed_refresh_preserves_cache_and_safe_error(self):
        self.put_contest()
        self.service.update_preferences(clist_username="test")
        with patch("voiceprompt.planner.ClistProvider") as provider:
            provider.return_value.fetch.side_effect = ContestFetchError("Service unavailable")
            self.service._sync(["clist"])
        self.assertEqual(len(self.service.snapshot()["contests"]), 1)
        self.assertEqual(self.service.snapshot()["sources"][0]["error"], "Service unavailable")

    def test_clist_key_is_not_in_local_database(self):
        with patch.object(self.service, "refresh_contests"):
            self.service.connect_clist("testuser", "private-test-key")
        self.service.credentials.save.assert_called_once_with("testuser", "private-test-key")
        self.assertNotIn(b"private-test-key", self.path.read_bytes())
        self.assertNotIn("private-test-key", str(self.service.snapshot()))

    def test_timezone_validation_and_dst(self):
        self.assertEqual(local_timestamp("2026-10-15 08:30", "Asia/Kolkata"), self.clock.wall)
        with self.assertRaises(ValueError):
            local_timestamp("2026-03-08 02:30", "America/New_York")
        due = next_alarm(local_timestamp("2026-10-16 12:00", "Asia/Kolkata"), 9, 0, [0], "Asia/Kolkata")
        self.assertEqual(due, local_timestamp("2026-10-19 09:00", "Asia/Kolkata"))


if __name__ == "__main__":
    unittest.main()
