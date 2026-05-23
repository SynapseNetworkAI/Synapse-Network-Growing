"""Shared metadata helpers for social reply distribution assets."""

from __future__ import annotations

import json

from server.database_social_distribution import SocialContentAssetRow


def reply_ids_from_asset(asset: SocialContentAssetRow) -> list[int]:
    metadata = _json_object(getattr(asset, "agent_metadata_json", None))
    reply_block = metadata.get("reply_block")
    if not isinstance(reply_block, dict):
        return []
    ids: list[int] = []
    for value in reply_block.get("reply_ids") or []:
        if isinstance(value, int):
            ids.append(value)
        elif isinstance(value, str) and value.isdigit():
            ids.append(int(value))
    return ids


def _json_object(value: str | None) -> dict[str, object]:
    try:
        payload = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
