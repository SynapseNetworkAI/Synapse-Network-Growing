"""Live public-feed readiness checks for AI visibility probes."""

from __future__ import annotations

from datetime import datetime, timezone

from server.services.growth import ai_visibility_feed_validation as feed_validation
from server.schemas_growth import (
    GrowthAIVisibilityLiveReadinessCheckOut,
    GrowthAIVisibilityLiveReadinessItemOut,
    GrowthAIVisibilityLiveReadinessOut,
)


def ai_visibility_live_readiness(
    *,
    feed_keys: list[str] | None = None,
    run_group: str | None = None,
) -> GrowthAIVisibilityLiveReadinessOut:
    generated_at = _utcnow()
    safe_run_group = (
        run_group or f"{generated_at.date().isoformat()}-live-readiness"
    ).strip()
    selected_feeds = feed_validation.parse_feed_keys(feed_keys)
    items = [
        _row_to_item(row)
        for feed_key in selected_feeds
        for row in feed_validation.validate_feed(
            feed_key=feed_key,
            run_group=safe_run_group,
        )
    ]
    ready_count = sum(1 for item in items if item.feed_ready)
    blocked_count = len(items) - ready_count
    return GrowthAIVisibilityLiveReadinessOut(
        generated_at=generated_at,
        run_group=safe_run_group,
        canonical_homepage=feed_validation.CANONICAL_HOMEPAGE,
        status="ready_for_external_probe" if blocked_count == 0 else "blocked",
        ready_count=ready_count,
        blocked_count=blocked_count,
        validation_command=_validation_command(
            feed_keys=selected_feeds,
            run_group=safe_run_group,
        ),
        apply_command=_apply_command(safe_run_group),
        items=items,
        total=len(items),
    )


def _row_to_item(row) -> GrowthAIVisibilityLiveReadinessItemOut:
    checks = _checks_from_row(row)
    feed_ready = _row_feed_ready(row)
    return GrowthAIVisibilityLiveReadinessItemOut(
        feed_key=row.feed_key,
        status="ready" if feed_ready else "blocked",
        feed_ready=feed_ready,
        external_probe_ready=feed_ready,
        run_group=row.run_group,
        platform=row.platform,
        query=row.query,
        answer_summary=row.answer_summary,
        checked_urls=[check.url for check in checks],
        missing_facts=list(row.missing_facts),
        next_action=row.next_action,
        checks=checks,
    )


def _checks_from_row(row) -> list[GrowthAIVisibilityLiveReadinessCheckOut]:
    metadata = row.metadata or {}
    raw_checks = metadata.get("checks") if isinstance(metadata, dict) else []
    if not isinstance(raw_checks, list):
        return []
    return [_check_to_out(check) for check in raw_checks if isinstance(check, dict)]


def _row_feed_ready(row) -> bool:
    return bool(row.synapse_mentioned and row.synapse_cited)


def _check_to_out(check: dict) -> GrowthAIVisibilityLiveReadinessCheckOut:
    status = int(check.get("status") or 0)
    error = str(check.get("error") or "")
    label = str(check.get("label") or "")
    return GrowthAIVisibilityLiveReadinessCheckOut(
        label=label,
        url=str(check.get("url") or ""),
        status=status,
        ok=not error
        and (200 <= status < 400 or (label == "mcp_unauth_post" and status == 401)),
        final_url=str(check.get("final_url") or ""),
        error=error,
        contains_synapse=bool(check.get("contains_synapse")),
    )


def _validation_command(*, feed_keys: list[str], run_group: str) -> str:
    feed_args = " ".join(f"--feed-key {feed_key}" for feed_key in feed_keys)
    output_path = (
        f"docs/archive/evidence/growth/ai-visibility/{run_group}-feed-validation.jsonl"
    )
    return (
        (
            "python scripts/growth/run_ai_visibility_feed_validation.py "
            f"{feed_args} --run-group {run_group} --output {output_path}"
        )
        .replace("  ", " ")
        .strip()
    )


def _apply_command(run_group: str) -> str:
    output_path = (
        f"docs/archive/evidence/growth/ai-visibility/{run_group}-feed-validation.jsonl"
    )
    return (
        "python scripts/growth/record_ai_visibility_probe.py "
        f"{output_path} --allow-local-validation --apply"
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
