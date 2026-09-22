from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from urllib import request

from google import genai
from google.genai import types

from voiceprompt.config import gemini_api_key, openrouter_api_key

SYSTEM_PROMPT = """You clean speech-to-text dictation for direct insertion.
Fix only obvious recognition errors, punctuation, casing, and spacing.
Preserve the speaker's meaning, wording, numbers, names, URLs, file paths, and code terms.
Return only the cleaned text. Never add commentary or quotation marks."""

_PROTECTED_TOKEN = re.compile(
    r"https?://\S+|\b[\w.+-]+@[\w.-]+\.\w+\b|\b0x[0-9a-fA-F]+\b|"
    r"\b\d+(?:\.\d+)?(?:%|ms|s|Hz|kHz|MHz|GB|MB|KB)?\b|"
    r"(?<!\w)(?:C\+\+|C#|\.NET|GPIO\d*|ESP32)(?!\w)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CleanupResult:
    text: str
    attempted: bool = False
    applied: bool = False
    provider: str = "none"
    error: str = ""


class CloudCleanup:
    def __init__(self, provider: str, openrouter_model: str, gemini_model: str, timeout_seconds: float = 4.0) -> None:
        self.provider = provider
        self.openrouter_model = openrouter_model
        self.gemini_model = gemini_model
        self.timeout_seconds = max(1.0, min(15.0, timeout_seconds))
        self._gemini_client: genai.Client | None = None

    @property
    def enabled(self) -> bool:
        return self.provider in {"openrouter", "gemini"}

    @property
    def available(self) -> bool:
        if self.provider == "openrouter":
            return bool(openrouter_api_key())
        if self.provider == "gemini":
            return bool(gemini_api_key())
        return False

    def clean(self, text: str) -> CleanupResult:
        if not self.enabled or not text.strip() or not self.available:
            return CleanupResult(text=text, provider=self.provider)
        try:
            cleaned = self._clean_openrouter(text) if self.provider == "openrouter" else self._clean_gemini(text)
            cleaned = cleaned.strip()
            if not self._acceptable(text, cleaned):
                return CleanupResult(text=text, attempted=True, provider=self.provider, error="cleanup rejected by integrity guard")
            return CleanupResult(text=cleaned, attempted=True, applied=cleaned != text, provider=self.provider)
        except Exception as exc:
            return CleanupResult(text=text, attempted=True, provider=self.provider, error=f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _acceptable(original: str, cleaned: str) -> bool:
        if not cleaned:
            return False
        if len(cleaned) > max(120, len(original) * 2.0) or len(cleaned) < len(original) * 0.5:
            return False
        lowered = cleaned.casefold()
        for token in _PROTECTED_TOKEN.findall(original):
            if token.casefold() not in lowered:
                return False
        return SequenceMatcher(None, original.casefold(), cleaned.casefold()).ratio() >= 0.45

    def _clean_openrouter(self, text: str) -> str:
        payload = {
            "model": self.openrouter_model or "openrouter/free",
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}],
            "temperature": 0,
            "max_tokens": min(512, max(64, len(text) // 2 + 32)),
            "provider": {"sort": "latency"},
        }
        api_request = request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {openrouter_api_key()}", "Content-Type": "application/json", "X-Title": "Voice Prompt"},
            method="POST",
        )
        with request.urlopen(api_request, timeout=self.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        return str(data["choices"][0]["message"]["content"])

    def _clean_gemini(self, text: str) -> str:
        response = self._get_gemini_client().models.generate_content(
            model=self.gemini_model,
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0,
                max_output_tokens=min(512, max(64, len(text) // 2 + 32)),
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        return response.text or ""

    def _get_gemini_client(self) -> genai.Client:
        if self._gemini_client is None:
            self._gemini_client = genai.Client(
                api_key=gemini_api_key(),
                http_options=types.HttpOptions(timeout=int(self.timeout_seconds * 1000)),
            )
        return self._gemini_client
