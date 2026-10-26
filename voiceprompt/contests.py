from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


PLATFORMS = {"codeforces": "Codeforces", "leetcode": "LeetCode", "codechef": "CodeChef", "atcoder": "AtCoder"}
HOSTS = {"codeforces": "codeforces.com", "leetcode": "leetcode.com", "codechef": "codechef.com", "atcoder": "atcoder.jp"}


def safe_contest_url(url: str, platform: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in {HOSTS.get(platform), "www." + HOSTS.get(platform, "")} and not parsed.username and not parsed.password


class ContestFetchError(RuntimeError):
    def __init__(self, message: str, retry_after: float = 60):
        super().__init__(message)
        self.retry_after = retry_after


def fetch_json(url: str, headers: dict | None = None) -> dict:
    request = Request(url, headers={"User-Agent": "VoicePrompt/1.0 (desktop contest reminders)", "Accept": "application/json"})
    for name, value in (headers or {}).items():
        request.add_unredirected_header(name, value)
    try:
        with urlopen(request, timeout=10) as response:
            content = response.read(8_000_001)
        if len(content) > 8_000_000:
            raise ContestFetchError("The contest response was unexpectedly large.")
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise ContestFetchError("Access denied. Check your API credentials or try again later.", 1800) from None
        if exc.code == 429:
            try:
                delay = float(exc.headers.get("Retry-After", "60"))
                delay = max(60, min(3600, delay)) if math.isfinite(delay) else 60
            except ValueError:
                delay = 60
            raise ContestFetchError("Contest service rate limit reached. Retrying later.", delay) from None
        raise ContestFetchError(f"Contest service returned HTTP {exc.code}.") from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise ContestFetchError("Could not read the contest service. Cached schedules remain available.") from None


@dataclass(frozen=True)
class Contest:
    id: str
    platform: str
    name: str
    url: str
    start: float
    end: float
    source: str

    def to_dict(self) -> dict:
        if not self.name.strip() or self.platform not in PLATFORMS or not safe_contest_url(self.url, self.platform):
            raise ContestFetchError("The contest service returned an invalid contest.")
        if not math.isfinite(self.start) or not math.isfinite(self.end) or self.end <= self.start:
            raise ContestFetchError("The contest service returned invalid dates.")
        return asdict(self)


def utc_timestamp(value: str) -> float:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # CLIST emits UTC when format_time=false, including in versions with no Z suffix.
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp()


class CodeforcesProvider:
    name = "codeforces"

    def fetch(self, now: float) -> list[dict]:
        payload = fetch_json("https://codeforces.com/api/contest.list?gym=false&lang=en")
        if payload.get("status") != "OK" or not isinstance(payload.get("result"), list):
            raise ContestFetchError("Codeforces could not return its contest list.")
        try:
            items = []
            for item in payload["result"]:
                if "startTimeSeconds" not in item:
                    continue
                start = float(item["startTimeSeconds"])
                end = start + float(item["durationSeconds"])
                if end <= now or start > now + 30 * 86400:
                    continue
                contest_id = int(item["id"])
                items.append(Contest(f"codeforces:{contest_id}", "codeforces", item["name"],
                                     f"https://codeforces.com/contest/{contest_id}", start, end, self.name).to_dict())
            return items
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ContestFetchError("Codeforces returned an unexpected contest format.") from None


class ClistCredentials:
    """Explicit Windows credential backend; never falls back to a plaintext keyring."""
    service = "VoicePrompt.CLIST"

    @staticmethod
    def _backend():
        try:
            from keyring.backends.Windows import WinVaultKeyring
            return WinVaultKeyring()
        except (ImportError, RuntimeError):
            raise ContestFetchError("Windows credential storage is unavailable. Install the app requirements.", 1800) from None

    def get(self, username: str) -> str:
        if not username:
            return ""
        try:
            return self._backend().get_password(self.service, username) or ""
        except ContestFetchError:
            raise
        except Exception:
            raise ContestFetchError("Unable to read the CLIST key from Windows credential storage.", 1800) from None

    def save(self, username: str, key: str) -> None:
        if not username.strip() or not key.strip():
            raise ValueError("Enter your CLIST username and API key.")
        try:
            self._backend().set_password(self.service, username.strip(), key.strip())
        except Exception:
            raise ContestFetchError("Unable to save the CLIST key in Windows credential storage.", 1800) from None


class ClistProvider:
    name = "clist"

    def __init__(self, username: str, key: str, wait=time.sleep):
        self.username, self.key, self.wait = username, key, wait

    def fetch(self, now: float) -> list[dict]:
        if not self.username or not self.key:
            raise ContestFetchError("CLIST is not connected. Enter your account username and API key.", 1800)
        auth = {"Authorization": f"ApiKey {self.username}:{self.key}"}
        query = {"resource__in": "leetcode.com,codechef.com,atcoder.jp", "end__gt": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                 "start__lt": datetime.fromtimestamp(now + 30 * 86400, timezone.utc).isoformat(),
                 "order_by": "start", "format_time": "false", "limit": 100, "format": "json"}
        items = []
        try:
            for page in range(20):
                if page:
                    self.wait(6.1)  # CLIST's documented limit is ten requests per minute.
                data = fetch_json("https://clist.by/api/v4/contest/?" + urlencode({**query, "offset": page * 100}), auth)
                if not isinstance(data.get("objects"), list) or not isinstance(data.get("meta"), dict):
                    raise ContestFetchError("CLIST returned an unexpected response format.")
                for item in data["objects"]:
                    platform = next((p for p, host in HOSTS.items() if item.get("resource") == host and p != "codeforces"), None)
                    if platform is None:
                        continue
                    start, end = utc_timestamp(item["start"]), utc_timestamp(item["end"])
                    if end > now and start <= now + 30 * 86400:
                        items.append(Contest(f"clist:{int(item['id'])}", platform, item["event"], item["href"], start, end, self.name).to_dict())
                if not data["meta"].get("next"):
                    return items
            raise ContestFetchError("CLIST pagination exceeded the limit; keeping the previous complete schedule.")
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ContestFetchError("CLIST returned an unexpected contest format.") from None
