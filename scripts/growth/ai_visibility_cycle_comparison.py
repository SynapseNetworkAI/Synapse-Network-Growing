from __future__ import annotations

from typing import Any

from scripts.growth.record_ai_visibility_probe import ProbeRecord
from server.services.growth.ai_visibility_comparison_status import (
    comparison_status_from_counts,
)
from server.services.growth.ai_visibility_official_sources import (
    is_official_citation_url,
)


def comparison_summary(
    *,
    current_external_records: list[ProbeRecord],
    previous_external_records: list[ProbeRecord],
    previous_source_path: str,
    provider_failure_count: int = 0,
) -> Any:
    current_mentions = sum(
        1 for record in current_external_records if record.synapse_mentioned
    )
    current_citations = sum(
        1 for record in current_external_records if record_has_official_citation(record)
    )
    previous_mentions = sum(
        1 for record in previous_external_records if record.synapse_mentioned
    )
    previous_citations = sum(
        1
        for record in previous_external_records
        if record_has_official_citation(record)
    )
    mentioned_delta = current_mentions - previous_mentions
    cited_delta = current_citations - previous_citations
    return {
        "previous_source_path": previous_source_path,
        "previous_external_probe_count": len(previous_external_records),
        "previous_mentioned_count": previous_mentions,
        "previous_cited_count": previous_citations,
        "mentioned_delta": mentioned_delta,
        "cited_delta": cited_delta,
        "comparison_status": comparison_status_from_counts(
            external_checks_count=(
                len(current_external_records) + provider_failure_count
            ),
            completed_external_count=len(current_external_records),
            previous_exists=bool(previous_external_records),
            mentioned_delta=mentioned_delta,
            cited_delta=cited_delta,
            provider_failure_count=provider_failure_count,
        ),
    }


def record_has_official_citation(record: ProbeRecord) -> bool:
    return any(is_official_citation_url(url) for url in record.cited_urls)
