"""Publisher metadata. A release build supplies a validated GitHub repository."""
import json
import re
from pathlib import Path


def repository():
    path = Path(__file__).with_name("release.json")
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("repository", "")
    except (OSError, ValueError, AttributeError):
        return ""
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value) else ""


def releases_url():
    value = repository()
    return f"https://github.com/{value}/releases" if value else ""
