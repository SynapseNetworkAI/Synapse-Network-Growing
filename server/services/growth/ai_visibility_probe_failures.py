from __future__ import annotations

from collections.abc import Iterable
from typing import Any

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


def provider_failure_summaries(records: Iterable[Any]) -> list[str]:
    by_platform: dict[str, int] = {}
    reasons: dict[str, str] = {}
    for record in records:
        platform = str(getattr(record, "platform", "") or "unknown")
        by_platform[platform] = by_platform.get(platform, 0) + 1
        reasons.setdefault(
            platform,
            _provider_failure_reason(list(getattr(record, "missing_facts", []) or [])),
        )
    return [
        (
            f"{platform} API probe failed for {count} query(s): "
            f"{reasons.get(platform) or 'provider request failed'}."
        )
        for platform, count in sorted(by_platform.items())
    ]


def _provider_failure_reason(missing_facts: list[str]) -> str:
    text = " ".join(str(item or "") for item in missing_facts).casefold()
    if "credit balance is too low" in text or "purchase credits" in text:
        return "credit balance is too low"
    if "monthly spending limit" in text or "used all available credits" in text:
        return "monthly spending limit or credits exhausted"
    if "quota exceeded" in text or "resource_exhausted" in text:
        return "quota exceeded"
    return "provider request failed"
