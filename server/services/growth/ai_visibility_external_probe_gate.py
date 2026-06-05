"""External answer-engine probe gate for AI visibility runs."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from server.schemas_growth import (
    GrowthAIVisibilityExternalProbeGateOut,
    GrowthAIVisibilityExternalProbeProviderOut,
)
from server.services.growth import ai_visibility_live_readiness
from server.services.growth.ai_visibility_text import unique_strings

TARGET_PLATFORMS = ["chatgpt", "claude", "grok"]
ENV_KEYS = {
    "chatgpt": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "grok": "XAI_API_KEY",
}
DEFAULT_FEED_KEY = "mcp_paid_api_discovery"


def ai_visibility_external_probe_gate(
    *,
    feed_key: str = DEFAULT_FEED_KEY,
    run_group: str | None = None,
) -> GrowthAIVisibilityExternalProbeGateOut:
    generated_at = datetime.now(timezone.utc)
    safe_feed_key = (feed_key or DEFAULT_FEED_KEY).strip()
    safe_run_group = _safe_run_group(
        generated_at=generated_at,
        feed_key=safe_feed_key,
        run_group=run_group,
    )
    readiness = _readiness(feed_key=safe_feed_key, run_group=safe_run_group)
    provider_readiness = _provider_readiness()
    provider_summary = _provider_summary(provider_readiness)
    ready_platforms = provider_summary["ready_platforms"]
    missing_platforms = provider_summary["missing_platforms"]
    feed_ready = _feed_ready(readiness)
    api_keys_ready = provider_summary["api_keys_ready"]
    blockers = _blockers(readiness=readiness, providers=provider_readiness)
    status = _status(
        feed_ready=feed_ready,
        api_keys_ready=api_keys_ready,
        ready_platforms=ready_platforms,
    )
    output_path = _output_path(safe_run_group)
    api_base = _api_base(feed_key=safe_feed_key, run_group=safe_run_group)
    partial_api_base = _partial_api_base(
        feed_key=safe_feed_key,
        run_group=safe_run_group,
        ready_platforms=ready_platforms,
    )
    return GrowthAIVisibilityExternalProbeGateOut(
        generated_at=generated_at,
        feed_key=safe_feed_key,
        run_group=safe_run_group,
        status=status,
        ready_to_execute=feed_ready and api_keys_ready,
        partial_ready_to_execute=feed_ready and bool(ready_platforms),
        feed_ready=feed_ready,
        api_keys_ready=api_keys_ready,
        target_platforms=TARGET_PLATFORMS,
        ready_platforms=ready_platforms,
        missing_platforms=missing_platforms,
        provider_readiness=provider_readiness,
        blockers=blockers,
        feed_validation_command=readiness.validation_command,
        record_readiness_command=readiness.apply_command,
        manual_probe_template_command=_manual_probe_template_command(
            feed_key=safe_feed_key,
            run_group=safe_run_group,
            output_path=output_path,
        ),
        api_readiness_command=api_base,
        api_execute_command=f"{api_base} --output {output_path} --execute",
        partial_api_readiness_command=partial_api_base,
        partial_api_execute_command=(
            f"{partial_api_base} --output {output_path} --execute"
            if partial_api_base
            else ""
        ),
        record_probe_command=(
            f"python scripts/growth/record_ai_visibility_probe.py {output_path} --apply"
        ),
        compare_command=(
            "curl -fsS "
            f"'http://localhost:9700/api/growth/ai-visibility/comparisons?feed_key={safe_feed_key}&run_group={safe_run_group}' "
            "| python -m json.tool"
        ),
    )


def _provider_readiness() -> list[GrowthAIVisibilityExternalProbeProviderOut]:
    return [
        GrowthAIVisibilityExternalProbeProviderOut(
            platform=platform,
            env_key=ENV_KEYS[platform],
            configured=bool(os.environ.get(ENV_KEYS[platform], "").strip()),
        )
        for platform in TARGET_PLATFORMS
    ]


def _safe_run_group(
    *, generated_at: datetime, feed_key: str, run_group: str | None
) -> str:
    return (
        run_group or f"{generated_at.date().isoformat()}-{feed_key}-external-probe"
    ).strip()


def _readiness(*, feed_key: str, run_group: str):
    return ai_visibility_live_readiness.ai_visibility_live_readiness(
        feed_keys=[feed_key],
        run_group=run_group,
    )


def _feed_ready(readiness) -> bool:
    return readiness.blocked_count == 0 and readiness.total > 0


def _provider_summary(
    providers: list[GrowthAIVisibilityExternalProbeProviderOut],
) -> dict[str, object]:
    ready = [item.platform for item in providers if item.configured]
    missing = [item.platform for item in providers if not item.configured]
    return {
        "ready_platforms": ready,
        "missing_platforms": missing,
        "api_keys_ready": not missing,
    }


def _output_path(run_group: str) -> str:
    return (
        f"docs/archive/evidence/growth/ai-visibility/{run_group}-external-probes.jsonl"
    )


def _api_base(*, feed_key: str, run_group: str) -> str:
    return (
        "python scripts/growth/run_ai_visibility_api_probe.py "
        f"--feed-key {feed_key} "
        f"--run-group {run_group} "
        "--platforms chatgpt,claude,grok"
    )


def _manual_probe_template_command(
    *, feed_key: str, run_group: str, output_path: str
) -> str:
    return (
        "python scripts/growth/generate_ai_visibility_probe_template.py "
        f"--feed-key {feed_key} "
        f"--run-group {run_group} "
        "--platforms chatgpt,claude,grok "
        "--mode after-feed "
        f"--output {output_path}"
    )


def _partial_api_base(
    *, feed_key: str, run_group: str, ready_platforms: list[str]
) -> str:
    partial_platform_arg = ",".join(ready_platforms)
    if not partial_platform_arg:
        return ""
    return (
        "python scripts/growth/run_ai_visibility_api_probe.py "
        f"--feed-key {feed_key} "
        f"--run-group {run_group} "
        f"--platforms {partial_platform_arg}"
    )


def _status(
    *,
    feed_ready: bool,
    api_keys_ready: bool,
    ready_platforms: list[str],
) -> str:
    if not feed_ready:
        return "blocked_until_feed_ready"
    if api_keys_ready:
        return "ready_to_execute_external_probes"
    if ready_platforms:
        return "ready_for_partial_external_probes"
    return "blocked_until_api_keys"


def _blockers(*, readiness, providers) -> list[str]:
    blockers: list[str] = []
    for item in readiness.items:
        blockers.extend(item.missing_facts)
        if item.next_action and not item.feed_ready:
            blockers.append(item.next_action)
    for provider in providers:
        if not provider.configured:
            blockers.append(f"{provider.platform} missing {provider.env_key}.")
    return unique_strings(blockers)
