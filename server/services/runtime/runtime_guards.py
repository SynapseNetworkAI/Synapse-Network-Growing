"""Runtime guard helpers for external provider failures and stop conditions."""

from __future__ import annotations


def is_openai_runtime_guard_error(message: str) -> bool:
    """Return whether an error should trigger the OpenAI runtime guard path."""

    text = (message or "").lower()
    return any(
        marker in text
        for marker in [
            "insufficient_quota",
            "you exceeded your current quota",
            "billing details",
            "model_not_found",
            "requested model",
            "does not exist",
            "invalid_api_key",
            "incorrect api key",
            "authentication",
            "organization not found",
        ]
    )
