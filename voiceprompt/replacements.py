from __future__ import annotations

import re


def apply_replacements(text: str, replacements: dict[str, str]) -> str:
    cleaned = text
    for source, target in replacements.items():
        source = source.strip()
        if not source:
            continue
        pattern = re.compile(rf"\b{re.escape(source)}\b", flags=re.IGNORECASE)
        cleaned = pattern.sub(target, cleaned)
    return cleaned.strip()
