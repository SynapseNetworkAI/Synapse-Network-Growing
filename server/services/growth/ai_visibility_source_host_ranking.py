"""Source-host ranking policy for AI visibility operator actions."""

from __future__ import annotations

from collections import Counter

from server.schemas_growth_ai_visibility_source_host import (
    GrowthAIVisibilitySourceHostActionOut,
)
from server.services.growth.ai_visibility_observed_source_hosts import (
    OBSERVED_SOURCE_HOST_ACTIONS,
)
from server.services.growth.ai_visibility_source_host_surfaces import (
    source_host_surface,
)
from server.services.growth.ai_visibility_text import unique_strings

SOURCE_HOST_ACTION_RESERVE = {
    "glama.ai",
    "lobehub.com",
    "mcpservers.org",
    "protodex.io",
    "pulsemcp.com",
    "smithery.ai",
}


def source_host_action_targets(
    source_hosts: Counter[str],
) -> list[GrowthAIVisibilitySourceHostActionOut]:
    return [
        _source_host_action_target(host, source_hosts[host])
        for host in source_hosts_for_actions(source_hosts)
    ]


def source_hosts_for_actions(source_hosts: Counter[str]) -> list[str]:
    reserve = [
        item for item in sorted(SOURCE_HOST_ACTION_RESERVE) if item in source_hosts
    ]
    ranked_limit = max(0, 10 - len(reserve))
    ranked = [
        item for item, _count in source_hosts.most_common() if item not in reserve
    ][:ranked_limit]
    return unique_strings(ranked + reserve)[:10]


def _source_host_action_target(
    host: str, count: int
) -> GrowthAIVisibilitySourceHostActionOut:
    config = OBSERVED_SOURCE_HOST_ACTIONS.get(host, {})
    return GrowthAIVisibilitySourceHostActionOut(
        host=host,
        surface=str(config.get("surface") or source_host_surface(host)),
        observed_count=count,
        priority=str(config.get("priority") or _priority_for_count(count)),
        draft_type=str(config.get("draft_type") or "contextual_source_host_review"),
        rationale=str(config.get("rationale") or _fallback_rationale(host)),
    )


def _priority_for_count(count: int) -> str:
    if count >= 2:
        return "p0"
    return "p1"


def _fallback_rationale(host: str) -> str:
    return (
        f"{host} appeared in answer-engine source hosts, so review whether Synapse "
        "needs a truthful listing, correction request, partner mention, or owned "
        "disambiguation refresh before the next unchanged probe."
    )
