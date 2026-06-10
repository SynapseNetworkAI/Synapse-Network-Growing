"""Answer-engine outcome aggregation for AI visibility cycles."""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from scripts.growth.record_ai_visibility_probe import ProbeRecord
from server.services.growth.ai_visibility_source_host_surfaces import (
    source_host_surface,
)

TARGET_PLATFORMS = ["chatgpt", "claude", "grok", "gemini"]


class OutcomeCount(BaseModel):
    value: str
    count: int
    surface: str | None = None


class PlatformOutcome(BaseModel):
    platform: str
    status: str
    probe_count: int
    mentioned_count: int
    cited_count: int
    source_hosts: list[OutcomeCount] = Field(default_factory=list)
    top_competitors: list[OutcomeCount] = Field(default_factory=list)
    next_action: str


class CycleOutcomes(BaseModel):
    platform_results: list[PlatformOutcome] = Field(default_factory=list)
    top_source_hosts: list[OutcomeCount] = Field(default_factory=list)
    top_competitors: list[OutcomeCount] = Field(default_factory=list)


def cycle_outcomes_for(records: list[ProbeRecord]) -> CycleOutcomes:
    return CycleOutcomes(
        platform_results=_platform_results_for(records),
        top_source_hosts=_source_host_counts_for(records),
        top_competitors=_competitor_counts_for(records),
    )


def _platform_results_for(records: list[ProbeRecord]) -> list[PlatformOutcome]:
    results: list[PlatformOutcome] = []
    for platform in TARGET_PLATFORMS:
        platform_records = [record for record in records if record.platform == platform]
        if not platform_records:
            results.append(
                PlatformOutcome(
                    platform=platform,
                    status="missing_probe",
                    probe_count=0,
                    mentioned_count=0,
                    cited_count=0,
                    next_action=f"Run the unchanged {platform} probe matrix.",
                )
            )
            continue
        mentioned_count = sum(
            1 for record in platform_records if record.synapse_mentioned
        )
        cited_count = sum(1 for record in platform_records if record.synapse_cited)
        source_hosts = _top_counts(_source_host_counter(platform_records), limit=8)
        top_competitors = _top_counts(_competitor_counter(platform_records), limit=8)
        results.append(
            PlatformOutcome(
                platform=platform,
                status=_platform_status(
                    mentioned_count=mentioned_count,
                    cited_count=cited_count,
                ),
                probe_count=len(platform_records),
                mentioned_count=mentioned_count,
                cited_count=cited_count,
                source_hosts=source_hosts,
                top_competitors=top_competitors,
                next_action=_platform_next_action(
                    platform=platform,
                    mentioned_count=mentioned_count,
                    cited_count=cited_count,
                    source_hosts=source_hosts,
                ),
            )
        )
    return results


def _source_host_counts_for(records: list[ProbeRecord]) -> list[OutcomeCount]:
    return _top_counts(_source_host_counter(records), limit=12, include_surface=True)


def _competitor_counts_for(records: list[ProbeRecord]) -> list[OutcomeCount]:
    return _top_counts(_competitor_counter(records), limit=12)


def _source_host_counter(records: list[ProbeRecord]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for record in records:
        hosts = record.metadata.get("source_hosts")
        if not isinstance(hosts, list):
            continue
        counter.update(str(host).strip().lower() for host in hosts if str(host).strip())
    return counter


def _competitor_counter(records: list[ProbeRecord]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for record in records:
        counter.update(
            str(item).strip()
            for item in record.competitor_mentions
            if str(item).strip()
        )
    return counter


def _top_counts(
    counter: Counter[str],
    *,
    limit: int,
    include_surface: bool = False,
) -> list[OutcomeCount]:
    items = []
    for value, count in counter.most_common(limit):
        surface = source_host_surface(value) if include_surface else None
        item = OutcomeCount(value=value, count=count, surface=surface)
        items.append(item)
    return items


def _platform_status(*, mentioned_count: int, cited_count: int) -> str:
    if cited_count:
        return "citation_observed"
    if mentioned_count:
        return "mention_observed"
    return "not_visible_yet"


def _platform_next_action(
    *,
    platform: str,
    mentioned_count: int,
    cited_count: int,
    source_hosts: list[OutcomeCount],
) -> str:
    if cited_count:
        return f"Preserve {platform} citation evidence and rerun stability probes."
    if mentioned_count:
        return f"Strengthen official citations for {platform} answer sources."
    if source_hosts:
        hosts = ", ".join(item.value for item in source_hosts[:3])
        return f"Feed or refresh source hosts observed by {platform}: {hosts}."
    return f"Run another unchanged {platform} probe after the next feed asset is live."
