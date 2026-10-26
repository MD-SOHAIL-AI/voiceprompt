from __future__ import annotations

import json
from urllib import request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google import genai

from voiceprompt.config import gemini_api_key, openrouter_api_key


SYSTEM_PROMPT = """You clean speech-to-text dictation for direct insertion.
Fix only obvious recognition errors, punctuation, casing, and spacing.
Preserve the speaker's meaning, wording, numbers, names, and code terms.
Return only the cleaned text. Never add commentary or quotation marks."""


class CloudCleanup:
    def __init__(
        self,
        provider: str,
        openrouter_model: str,
        gemini_model: str,
        timeout_seconds: float = 4.0,
    ) -> None:
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

    def clean(self, text: str) -> str:
        if not self.enabled or not text.strip() or not self.available:
            return text
        try:
            cleaned = self._clean_openrouter(text) if self.provider == "openrouter" else self._clean_gemini(text)
            cleaned = cleaned.strip()
            if not cleaned:
                return text
            if len(cleaned) > max(120, len(text) * 2.5) or len(cleaned) < len(text) * 0.35:
                return text
            return cleaned
        except Exception:
            return text

    def _clean_openrouter(self, text: str) -> str:
        payload = {
            "model": self.openrouter_model or "openrouter/free",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0,
            "max_tokens": min(512, max(64, len(text) // 2 + 32)),
            "provider": {"sort": "latency"},
        }
        api_request = request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {openrouter_api_key()}",
                "Content-Type": "application/json",
                "X-Title": "VoicePrompt",
            },
            method="POST",
        )
        with request.urlopen(api_request, timeout=self.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        return str(data["choices"][0]["message"]["content"])

    def _clean_gemini(self, text: str) -> str:
        from google.genai import types

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
            from google import genai
            from google.genai import types

            self._gemini_client = genai.Client(
                api_key=gemini_api_key(),
                http_options=types.HttpOptions(timeout=int(self.timeout_seconds * 1000)),
            )
        return self._gemini_client
