#!/usr/bin/env python3
"""Diagnose post-probe AI visibility gaps and recommend source-host actions."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.growth.ai_visibility_cli import (  # noqa: E402
    emit_failure,
    write_json_payload,
    write_text_or_stdout,
)
from scripts.growth.record_ai_visibility_probe import (  # noqa: E402
    ProbeRecord,
    parse_probe_file,
    validate_records,
)
from server.services.growth.ai_visibility_feed_diagnosis_models import (  # noqa: E402
    API_MONETIZATION_COMPETITORS,
    BRAND_COLLISIONS,
    CompetitorMap,
    FeedDiagnosis,
    FeedDiagnosisCommands,
    FeedDiagnosisIssue,
    FeedDiagnosisScope,
    SourceHostExecution,
    TARGET_PLATFORMS,
)
from server.services.growth.ai_visibility_text import unique_strings  # noqa: E402


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description=("Generate source-host recommendations after AI visibility probes.")
    )
    parser.add_argument("probe_file", help="JSON/JSONL probe evidence file.")
    parser.add_argument("--output", help="Write diagnosis JSON to this path.")
    parser.add_argument(
        "--recommendations-output",
        help="Optional JSONL file containing recommended source-host executions.",
    )
    args = parser.parse_args()

    try:
        records = parse_probe_file(Path(args.probe_file))
        errors = validate_records(records, allow_local_validation=True)
        if errors:
            write_json_payload({"status": "failed", "errors": errors}, None)
            return 2
        diagnosis = diagnose_feed(records, source_path=args.probe_file)
        write_json_payload(diagnosis.model_dump(), args.output)
        if args.recommendations_output:
            write_recommendations_jsonl(
                [
                    item.model_dump()
                    for item in diagnosis.recommended_source_host_executions
                ],
                args.recommendations_output,
            )
        return 2 if diagnosis.status == "no_external_probe_evidence" else 0
    except Exception as exc:
        emit_failure(exc)
        return 1


def diagnose_feed(records: list[ProbeRecord], *, source_path: str) -> FeedDiagnosis:
    external_records, blocker_records = external_and_blocker_records(records)
    scope = scope_for(records)
    target_platforms = target_platforms_for(external_records)
    covered_platforms = sorted(
        {record.platform for record in external_records if record.platform}
    )
    competitor_map = competitors_by_name(external_records)
    issues = issue_list(external_records, blocker_records, competitor_map)
    recommendations = recommendations_for(
        feed_key=scope.feed_key,
        run_group=scope.run_group,
        external_records=external_records,
        target_platforms=target_platforms,
        competitor_map=competitor_map,
    )
    return FeedDiagnosis(
        status=diagnosis_status(external_records, blocker_records),
        generated_at=datetime.now(UTC).isoformat(),
        source_path=source_path,
        feed_key=scope.feed_key,
        run_group=scope.run_group,
        feed_keys=scope.feed_keys,
        run_groups=scope.run_groups,
        record_count=len(records),
        external_probe_count=len(external_records),
        api_probe_blocker_count=len(blocker_records),
        external_mentioned_count=sum(
            1 for record in external_records if record.synapse_mentioned
        ),
        external_cited_count=sum(
            1 for record in external_records if record.synapse_cited
        ),
        target_platforms=target_platforms,
        covered_platforms=covered_platforms,
        competitors=sorted(competitor_map.by_name),
        issues=issues,
        recommended_source_host_executions=recommendations,
        commands=FeedDiagnosisCommands(
            record_probe=(
                "python scripts/growth/record_ai_visibility_probe.py "
                f"{source_path} --apply"
            ),
            summarize_cycle=(
                f"python scripts/growth/summarize_ai_visibility_cycle.py {source_path}"
            ),
            rerun_api_probe=api_probe_command(
                feed_key=scope.feed_key,
                run_group=f"{scope.run_group}-after-source-hosts",
                platforms=target_platforms,
            ),
        ),
    )


def external_and_blocker_records(
    records: list[ProbeRecord],
) -> tuple[list[ProbeRecord], list[ProbeRecord]]:
    blockers = [record for record in records if is_api_probe_readiness_blocker(record)]
    external = [
        record
        for record in records
        if not is_local_validation(record)
        and not is_api_probe_readiness_blocker(record)
    ]
    return external, blockers


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


def competitors_by_name(records: list[ProbeRecord]) -> CompetitorMap:
    result: dict[str, list[str]] = {}
    for record in records:
        for competitor in record.competitor_mentions:
            key = normalize_name(competitor)
            if not key:
                continue
            result.setdefault(key, [])
            result[key] = unique_strings(result[key] + [record.query])
    return CompetitorMap(by_name=result)


def issue_list(
    external_records: list[ProbeRecord],
    blocker_records: list[ProbeRecord],
    competitor_map: CompetitorMap,
) -> list[FeedDiagnosisIssue]:
    return probe_evidence_issues(external_records, blocker_records) + competitor_issues(
        competitor_map
    )


def probe_evidence_issues(
    external_records: list[ProbeRecord], blocker_records: list[ProbeRecord]
) -> list[FeedDiagnosisIssue]:
    issues = []
    if blocker_records and not external_records:
        issues.append(
            FeedDiagnosisIssue(
                issue_key="api_probe_blocked",
                severity="p0",
                summary="Answer-engine API probe keys are missing or not visible to the runner.",
            )
        )
    if not external_records:
        issues.append(
            FeedDiagnosisIssue(
                issue_key="no_external_probe_evidence",
                severity="p0",
                summary="No ChatGPT, Claude, Grok, Gemini, or public search rows were recorded.",
            )
        )
    elif not any(record.synapse_mentioned for record in external_records):
        issues.append(
            FeedDiagnosisIssue(
                issue_key="platform_missing_official_identity",
                severity="p0",
                summary="External answer engines did not mention Synapse Network.",
            )
        )
    if external_records and not any(
        record.synapse_cited for record in external_records
    ):
        issues.append(
            FeedDiagnosisIssue(
                issue_key="platform_missing_official_citation",
                severity="p0",
                summary="External answer engines did not cite official Synapse URLs.",
            )
        )
    return issues


def competitor_issues(competitor_map: CompetitorMap) -> list[FeedDiagnosisIssue]:
    issues = []
    collision_terms = sorted(set(competitor_map.by_name) & BRAND_COLLISIONS)
    if collision_terms:
        issues.append(
            FeedDiagnosisIssue(
                issue_key="brand_collision_returned",
                severity="p0",
                summary="Probe answers returned non-Synapse-Network Synapse entities.",
                terms=collision_terms,
            )
        )
    monetization_terms = sorted(
        set(competitor_map.by_name) & API_MONETIZATION_COMPETITORS
    )
    if monetization_terms:
        issues.append(
            FeedDiagnosisIssue(
                issue_key="api_monetization_competitors_returned",
                severity="p1",
                summary="Probe answers preferred incumbent API monetization or payment alternatives.",
                terms=monetization_terms,
            )
        )
    return issues


def recommendations_for(
    *,
    feed_key: str,
    run_group: str,
    external_records: list[ProbeRecord],
    target_platforms: list[str],
    competitor_map: CompetitorMap,
) -> list[SourceHostExecution]:
    if not external_records:
        return [
            missing_external_probe_recommendation(feed_key, run_group, target_platforms)
        ]
    all_queries = unique_strings([record.query for record in external_records])
    collision_queries = (
        queries_for_terms(competitor_map, BRAND_COLLISIONS) or all_queries
    )
    monetization_queries = (
        queries_for_terms(competitor_map, API_MONETIZATION_COMPETITORS) or all_queries
    )
    rerun = api_probe_command(
        feed_key=feed_key,
        run_group=f"{run_group}-after-source-hosts",
        platforms=target_platforms,
    )
    return source_host_recommendations(
        all_queries=all_queries,
        collision_queries=collision_queries,
        monetization_queries=monetization_queries,
        rerun=rerun,
        target_platforms=target_platforms,
    )


def missing_external_probe_recommendation(
    feed_key: str, run_group: str, target_platforms: list[str]
) -> SourceHostExecution:
    return source_host_execution(
        surface="probe_rerun",
        draft_type="four_platform_probe",
        priority="p0",
        platforms=target_platforms,
        queries=[],
        rationale="No external answer-engine rows exist for this cycle.",
        brief=(
            "Run the complete ChatGPT, Claude, Grok, and Gemini probe before "
            "source-host diagnosis."
        ),
        validation=(
            "python scripts/growth/run_ai_visibility_api_probe.py "
            "--platforms chatgpt,claude,grok,gemini"
        ),
        next_probe=api_probe_command(feed_key, run_group, target_platforms),
    )


def source_host_recommendations(
    *,
    all_queries: list[str],
    collision_queries: list[str],
    monetization_queries: list[str],
    rerun: str,
    target_platforms: list[str],
) -> list[SourceHostExecution]:
    return [
        source_host_execution(
            surface="official_mcp_registry",
            draft_type="mcp_directory_listing",
            priority="p0",
            platforms=["chatgpt", "claude", "gemini"],
            queries=all_queries,
            rationale="Official protocol registries are high-trust source hosts for MCP client and model discovery.",
            brief=(
                "Verify the Synapse Remote MCP listing names Synapse Network as the "
                "MCP server for paid API calls, AgentPay, USDC settlement, and "
                "discover_services/invoke_and_pay/get_receipt tools."
            ),
            validation="mcp-publisher publish && curl 'https://registry.modelcontextprotocol.io/v0.1/servers?search=synapse'",
            next_probe=rerun,
        ),
        source_host_execution(
            surface="github_readme",
            draft_type="github_readme_answer_block",
            priority="p0",
            platforms=target_platforms,
            queries=all_queries,
            rationale="Answer engines frequently use GitHub repositories as stable technical source hosts.",
            brief=(
                "Add a compact answer block to the MCP server README: what Synapse "
                "Network is, hosted MCP endpoint, supported tools, BYOK/OAuth auth, "
                "and why it differs from Stripe, RapidAPI, and x402."
            ),
            validation="git grep -n 'MCP server for paid API calls' README.md server.json",
            next_probe=rerun,
        ),
        source_host_execution(
            surface="smithery",
            draft_type="mcp_directory_listing",
            priority="p1",
            platforms=["claude", "chatgpt", "gemini"],
            queries=all_queries,
            rationale="Third-party MCP directories give answer engines an independent listing beyond Synapse-owned pages.",
            brief=(
                "Submit or refresh Smithery metadata with the hosted MCP endpoint, "
                "npm stdio package, paid API monetization category, and tool names."
            ),
            validation="smithery inspect @synapse-network-ai/mcp-server",
            next_probe=rerun,
        ),
        source_host_execution(
            surface="glama",
            draft_type="mcp_directory_listing",
            priority="p1",
            platforms=["claude", "chatgpt", "gemini"],
            queries=all_queries,
            rationale="Glama is a public MCP discovery source that can reinforce independent category evidence.",
            brief=(
                "Submit or refresh Glama listing copy for SynapseNetwork MCP Server "
                "with AgentPay, API monetization, and hosted Remote MCP URL."
            ),
            validation="curl -fsS 'https://glama.ai/search?q=Synapse%20Network%20MCP'",
            next_probe=rerun,
        ),
        source_host_execution(
            surface="x_citation_thread",
            draft_type="social_citation_thread",
            priority="p1",
            platforms=["grok"],
            queries=monetization_queries,
            rationale="Grok and web-search engines can benefit from public social citations tied to live docs and GitHub URLs.",
            brief=(
                "Draft a human-approved X thread comparing Synapse with Stripe, "
                "RapidAPI, and x402 for agent-paid API calls; link docs, GitHub, "
                "and the Remote MCP endpoint."
            ),
            validation="Record the published X URL as source-host evidence after human approval.",
            next_probe=rerun,
        ),
        source_host_execution(
            surface="docs_disambiguation_links",
            draft_type="answer_page_refresh",
            priority="p1",
            platforms=target_platforms,
            queries=collision_queries,
            rationale="Brand-collision entities appeared in answers, so source hosts need repeated official identity language.",
            brief=(
                "Refresh Synapse docs and directory copy with disambiguation: "
                "Synapse Network at synapse-network.ai is not Azure Synapse "
                "Analytics, Project Synapse, Sage Bionetworks Synapse, or mcpsynapse.dev."
            ),
            validation="curl -fsS https://docs.synapse-network.ai/mcp/paid-api-calls | grep -i 'Azure Synapse'",
            next_probe=rerun,
        ),
    ]


def source_host_execution(
    *,
    surface: str,
    draft_type: str,
    priority: str,
    platforms: list[str],
    queries: list[str],
    rationale: str,
    brief: str,
    validation: str,
    next_probe: str,
) -> SourceHostExecution:
    return SourceHostExecution(
        surface=surface,
        draft_type=draft_type,
        priority=priority,
        target_platforms=[item for item in platforms if item in TARGET_PLATFORMS],
        target_queries=queries[:8],
        rationale=rationale,
        content_brief=brief,
        validation_command=validation,
        next_probe_command=next_probe,
    )


def queries_for_terms(competitor_map: CompetitorMap, terms: set[str]) -> list[str]:
    return unique_strings(
        [
            query
            for term, queries in competitor_map.by_name.items()
            if term in terms
            for query in queries
        ]
    )


def diagnosis_status(
    external_records: list[ProbeRecord], blocker_records: list[ProbeRecord]
) -> str:
    if not external_records:
        if blocker_records:
            return "external_probe_blocked"
        return "no_external_probe_evidence"
    if any(record.synapse_cited for record in external_records):
        return "citation_observed"
    return "source_host_actions_required"


def api_probe_command(feed_key: str, run_group: str, platforms: list[str]) -> str:
    platform_arg = ",".join(platforms or TARGET_PLATFORMS)
    return (
        "python scripts/growth/run_ai_visibility_api_probe.py "
        f"--feed-key {feed_key} --run-group {run_group} "
        f"--platforms {platform_arg} --execute"
    )


def is_local_validation(record: ProbeRecord) -> bool:
    return record.platform.endswith("_validation")


def is_api_probe_readiness_blocker(record: ProbeRecord) -> bool:
    return str(record.metadata.get("mode", "")).strip() == "api_probe_readiness_blocker"


def normalize_name(value: str) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").split())


def write_recommendations_jsonl(
    recommendations: list[dict[str, Any]], output: str
) -> None:
    rendered = "\n".join(
        json.dumps(item, ensure_ascii=False) for item in recommendations
    )
    write_text_or_stdout(rendered, output=output)


if __name__ == "__main__":
    raise SystemExit(main())
