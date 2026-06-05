"""Robots.txt policy helpers for answer-engine crawler readiness."""

from __future__ import annotations

from typing import Any

AI_SEARCH_CRAWLERS = [
    "OAI-SearchBot",
    "ChatGPT-User",
    "GPTBot",
    "ClaudeBot",
    "Claude-User",
    "Claude-SearchBot",
    "anthropic-ai",
    "PerplexityBot",
    "Bingbot",
    "Google-Extended",
]


def robots_ai_crawler_policy(robots_txt: str) -> Any:
    normalized = robots_txt.lower()
    explicit = [
        crawler for crawler in AI_SEARCH_CRAWLERS if crawler.lower() in normalized
    ]
    blocked = blocked_ai_crawlers(robots_txt)
    return {
        "required_crawlers": AI_SEARCH_CRAWLERS,
        "explicit_crawlers": explicit,
        "missing_explicit_crawlers": [
            crawler for crawler in AI_SEARCH_CRAWLERS if crawler not in explicit
        ],
        "blocked_crawlers": blocked,
        "wildcard_allows_public": wildcard_allows_public(robots_txt),
        "policy_mode": "explicit" if explicit else "wildcard",
    }


def blocked_ai_crawlers(robots_txt: str) -> list[str]:
    groups = parse_robots_groups(robots_txt)
    blocked: list[str] = []
    for crawler in AI_SEARCH_CRAWLERS:
        relevant = [
            group
            for group in groups
            if "*" in group["agents"] or crawler.lower() in group["agents"]
        ]
        if any(group_blocks_public(group) for group in relevant):
            blocked.append(crawler)
    return blocked


def wildcard_allows_public(robots_txt: str) -> bool:
    for group in parse_robots_groups(robots_txt):
        if "*" not in group["agents"]:
            continue
        if group_blocks_public(group):
            return False
        if "/" in group["allows"] or not group["disallows"]:
            return True
    return False


def parse_robots_groups(robots_txt: str) -> list[dict[str, set[str]]]:
    groups: list[dict[str, set[str]]] = []
    current: dict[str, set[str]] | None = None
    for raw_line in robots_txt.splitlines():
        parsed = _robots_directive(raw_line)
        if parsed is None:
            continue
        key, value = parsed
        if key == "user-agent":
            current = _robots_agent_group(groups, current)
            current["agents"].add(value)
        elif key in {"allow", "disallow"} and current is not None:
            _add_robots_path(current, key=key, value=value)
    return groups


def group_blocks_public(group: dict[str, set[str]]) -> bool:
    disallows = group["disallows"]
    allows = group["allows"]
    return "/" in disallows and "/" not in allows


def _robots_directive(raw_line: str) -> tuple[str, str] | None:
    line = raw_line.split("#", 1)[0].strip()
    if not line or ":" not in line:
        return None
    key, value = [part.strip().lower() for part in line.split(":", 1)]
    return key, value


def _robots_agent_group(
    groups: list[dict[str, set[str]]],
    current: dict[str, set[str]] | None,
) -> dict[str, set[str]]:
    if current is not None and not current["allows"] and not current["disallows"]:
        return current
    next_group = {"agents": set(), "allows": set(), "disallows": set()}
    groups.append(next_group)
    return next_group


def _add_robots_path(
    current: dict[str, set[str]],
    *,
    key: str,
    value: str,
) -> None:
    target = "allows" if key == "allow" else "disallows"
    current[target].add(value or "")
