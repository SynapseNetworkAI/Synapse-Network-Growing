"""Source-host ranking policy for AI visibility operator actions."""

from __future__ import annotations

from collections import Counter

from server.services.growth.ai_visibility_text import unique_strings

SOURCE_HOST_ACTION_RESERVE = {
    "glama.ai",
    "mcpservers.org",
    "smithery.ai",
}


def source_hosts_for_actions(source_hosts: Counter[str]) -> list[str]:
    ranked = [item for item, _count in source_hosts.most_common(8)]
    reserve = [
        item
        for item in sorted(SOURCE_HOST_ACTION_RESERVE)
        if item in source_hosts and item not in ranked
    ]
    return unique_strings(ranked + reserve)[:10]
