"""Record partition helpers for AI visibility feed diagnosis."""

from __future__ import annotations

from scripts.growth.record_ai_visibility_probe import ProbeRecord
from server.services.growth.ai_visibility_feed_diagnosis_models import (
    FeedDiagnosisScope,
    TARGET_PLATFORMS,
)
from server.services.growth.ai_visibility_probe_failures import (
    has_provider_failure_missing_fact,
)


def external_blocker_and_failure_records(
    records: list[ProbeRecord],
) -> tuple[list[ProbeRecord], list[ProbeRecord], list[ProbeRecord]]:
    blockers = [record for record in records if is_api_probe_readiness_blocker(record)]
    external_candidates = [
        record
        for record in records
        if not is_local_validation(record)
        and not is_api_probe_readiness_blocker(record)
    ]
    provider_failures = [
        record for record in external_candidates if is_provider_failure(record)
    ]
    external = [
        record for record in external_candidates if not is_provider_failure(record)
    ]
    return external, blockers, provider_failures


def scope_for(records: list[ProbeRecord]) -> FeedDiagnosisScope:
    feed_keys = sorted({record.feed_key for record in records if record.feed_key})
    run_groups = sorted({record.run_group for record in records if record.run_group})
    return FeedDiagnosisScope(
        feed_keys=feed_keys,
        run_groups=run_groups,
        feed_key=feed_keys[0] if len(feed_keys) == 1 else "mixed",
        run_group=run_groups[0] if len(run_groups) == 1 else "mixed",
    )


def target_platforms_for(external_records: list[ProbeRecord]) -> list[str]:
    observed = {record.platform for record in external_records}
    if not observed:
        return TARGET_PLATFORMS
    ordered = [platform for platform in TARGET_PLATFORMS if platform in observed]
    extra = sorted(observed - set(TARGET_PLATFORMS))
    return ordered + extra


def diagnosis_status(
    external_records: list[ProbeRecord],
    blocker_records: list[ProbeRecord],
    provider_failure_records: list[ProbeRecord],
) -> str:
    if not external_records:
        if blocker_records or provider_failure_records:
            return "external_probe_blocked"
        return "no_external_probe_evidence"
    if provider_failure_records:
        return "partial_external_probe"
    if any(record.synapse_cited for record in external_records):
        return "citation_observed"
    return "source_host_actions_required"


def is_local_validation(record: ProbeRecord) -> bool:
    return record.platform.endswith("_validation")


def is_api_probe_readiness_blocker(record: ProbeRecord) -> bool:
    return str(record.metadata.get("mode", "")).strip() == "api_probe_readiness_blocker"


def is_provider_failure(record: ProbeRecord) -> bool:
    return has_provider_failure_missing_fact(record.missing_facts)
