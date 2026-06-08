from __future__ import annotations

from collections.abc import Iterable

API_KEY_MARKERS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "GEMINI_API_KEY",
    "GENIMI_API_KEY",
)
PROVIDER_FAILURE_MARKER = " API probe failed:"


def is_external_api_key_setup_blocker(value: str) -> bool:
    text = str(value or "")
    return any(marker in text for marker in API_KEY_MARKERS)


def is_provider_failure_missing_fact(value: str) -> bool:
    return PROVIDER_FAILURE_MARKER in str(value or "")


def has_provider_failure_missing_fact(values: Iterable[str]) -> bool:
    return any(is_provider_failure_missing_fact(value) for value in values)
