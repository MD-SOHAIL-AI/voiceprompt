from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from voiceprompt.contests import ClistCredentials, ClistProvider, CodeforcesProvider, ContestFetchError, fetch_json, safe_contest_url


class ContestProviderTests(unittest.TestCase):
    @patch("voiceprompt.contests.fetch_json")
    def test_codeforces_filters_completed_and_far_future_and_uses_public_api(self, fetch):
        fetch.return_value = {"status": "OK", "result": [
            {"id": 1, "name": "Upcoming", "startTimeSeconds": 2000, "durationSeconds": 3600},
            {"id": 2, "name": "Over", "startTimeSeconds": 0, "durationSeconds": 60},
            {"id": 3, "name": "Distant", "startTimeSeconds": 9999999, "durationSeconds": 60}]}
        contests = CodeforcesProvider().fetch(1000)
        self.assertEqual([c["id"] for c in contests], ["codeforces:1"])
        self.assertNotIn("apiKey", fetch.call_args.args[0])

    @patch("voiceprompt.contests.fetch_json")
    def test_clist_pagination_utc_normalization_and_authentication_header(self, fetch):
        contest = {"id": 1, "event": "ABC", "resource": "atcoder.jp", "href": "https://atcoder.jp/contests/abc1",
                   "start": "2026-10-15T10:00:00", "end": "2026-10-15T12:00:00Z"}
        fetch.side_effect = [{"objects": [contest], "meta": {"next": "?offset=100"}}, {"objects": [], "meta": {"next": None}}]
        wait = MagicMock()
        result = ClistProvider("user", "key", wait).fetch(1792050000)
        self.assertEqual(len(result), 1)
        wait.assert_called_once_with(6.1)
        self.assertEqual(fetch.call_args_list[0].args[1], {"Authorization": "ApiKey user:key"})
        self.assertNotIn("key", fetch.call_args.args[0])
        self.assertIn("offset=100", fetch.call_args.args[0])

    @patch("voiceprompt.contests.fetch_json")
    def test_partial_page_failure_is_not_returned_as_complete_schedule(self, fetch):
        fetch.side_effect = [{"objects": [], "meta": {"next": "?offset=100"}}, ContestFetchError("offline")]
        with self.assertRaisesRegex(ContestFetchError, "offline"):
            ClistProvider("user", "key", lambda _: None).fetch(1000)

    @patch("voiceprompt.contests.fetch_json")
    def test_missing_credentials_make_no_network_request(self, fetch):
        with self.assertRaisesRegex(ContestFetchError, "not connected"):
            ClistProvider("", "").fetch(1000)
        fetch.assert_not_called()

    def test_only_expected_https_contest_links_are_openable(self):
        self.assertTrue(safe_contest_url("https://www.codechef.com/START1", "codechef"))
        for url in ("javascript:alert(1)", "https://evil.example/", "https://codechef.com.evil.example/a", "https://user:password@codechef.com/"):
            self.assertFalse(safe_contest_url(url, "codechef"))

    @patch("voiceprompt.contests.ClistCredentials._backend")
    def test_secure_storage_errors_do_not_expose_key(self, backend):
        backend.return_value.set_password.side_effect = RuntimeError("secret-key")
        with self.assertRaises(ContestFetchError) as caught:
            ClistCredentials().save("user", "secret-key")
        self.assertNotIn("secret-key", str(caught.exception))

    @patch("voiceprompt.contests.urlopen")
    def test_provider_errors_do_not_expose_headers(self, open_url):
        from urllib.error import HTTPError
        open_url.side_effect = HTTPError("https://clist.by/", 401, "private", {}, None)
        with self.assertRaises(ContestFetchError) as caught:
            fetch_json("https://clist.by/", {"Authorization": "private"})
        self.assertNotIn("private", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
