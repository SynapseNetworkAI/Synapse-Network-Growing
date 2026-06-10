"""Source-host ranking policy for AI visibility operator actions."""

from __future__ import annotations

from collections import Counter

from server.services.growth.ai_visibility_text import unique_strings

SOURCE_HOST_ACTION_RESERVE = {
    "glama.ai",
    "lobehub.com",
    "mcpservers.org",
    "protodex.io",
    "pulsemcp.com",
    "smithery.ai",
}


def source_hosts_for_actions(source_hosts: Counter[str]) -> list[str]:
    reserve = [
        item
        for item in sorted(SOURCE_HOST_ACTION_RESERVE)
        if item in source_hosts
    ]
    ranked_limit = max(0, 10 - len(reserve))
    ranked = [
        item
        for item, _count in source_hosts.most_common()
        if item not in reserve
    ][:ranked_limit]
    return unique_strings(ranked + reserve)[:10]
