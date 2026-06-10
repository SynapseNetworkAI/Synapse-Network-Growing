from __future__ import annotations


def comparison_status_from_counts(
    *,
    external_checks_count: int,
    completed_external_count: int,
    previous_exists: bool,
    mentioned_delta: int,
    cited_delta: int,
    provider_failure_count: int = 0,
) -> str:
    if _has_no_external_checks(external_checks_count):
        return "needs_external_probe"
    if _has_only_provider_failures(
        completed_external_count=completed_external_count,
        provider_failure_count=provider_failure_count,
    ):
        return "inconclusive_provider_failure"
    if not previous_exists:
        if _has_provider_failures(provider_failure_count):
            return "inconclusive_provider_failure"
        return "baseline"
    return _delta_status(
        mentioned_delta=mentioned_delta,
        cited_delta=cited_delta,
        provider_failure_count=provider_failure_count,
    )


def _has_no_external_checks(external_checks_count: int) -> bool:
    return external_checks_count <= 0


def _has_only_provider_failures(
    *, completed_external_count: int, provider_failure_count: int
) -> bool:
    return completed_external_count <= 0 and provider_failure_count > 0


def _has_provider_failures(provider_failure_count: int) -> bool:
    return provider_failure_count > 0


def _delta_status(
    *,
    mentioned_delta: int,
    cited_delta: int,
    provider_failure_count: int,
) -> str:
    if mentioned_delta > 0 or cited_delta > 0:
        return "improved"
    if _has_provider_failures(provider_failure_count):
        return "inconclusive_provider_failure"
    if mentioned_delta < 0 or cited_delta < 0:
        return "regressed"
    return "flat"
