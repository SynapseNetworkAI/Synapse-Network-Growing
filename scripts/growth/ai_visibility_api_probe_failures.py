from __future__ import annotations

import os
from typing import Any


MODEL_ENV_KEYS = {
    "chatgpt": "OPENAI_AI_VISIBILITY_MODEL",
    "claude": "ANTHROPIC_AI_VISIBILITY_MODEL",
    "grok": "XAI_AI_VISIBILITY_MODEL",
}


def provider_failure_payload(
    *,
    platform: str,
    query: str,
    default_models: dict[str, str],
    redacted_error: str,
) -> dict[str, Any]:
    model = os.environ.get(
        MODEL_ENV_KEYS.get(platform, ""),
        default_models.get(platform, "unknown"),
    )
    return {
        "summary": f"{platform} API probe failed for {query!r}: {redacted_error[:800]}",
        "synapse_mentioned": False,
        "synapse_cited": False,
        "cited_urls": [],
        "source_urls": [],
        "competitor_mentions": [],
        "missing_facts": [f"{platform} API probe failed: {redacted_error[:500]}"],
        "next_action": "Fix provider/API probe failure and rerun the same query.",
        "result_rank": 0,
        "model": model,
        "request_id": "",
        "platform": platform,
    }
