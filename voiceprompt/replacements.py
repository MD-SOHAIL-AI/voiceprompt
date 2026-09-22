from __future__ import annotations

import re


def apply_replacements(text: str, replacements: dict[str, str]) -> str:
    cleaned = text
    # Longest first avoids a short phrase consuming part of a longer phrase.
    items = sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True)
    for source, target in items:
        source = source.strip()
        if not source:
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(source)}(?!\w)", flags=re.IGNORECASE)
        cleaned = pattern.sub(lambda _match, value=target: value, cleaned)
    return cleaned.strip()
