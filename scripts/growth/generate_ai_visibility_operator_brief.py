#!/usr/bin/env python3
"""Export a Markdown operator brief for one AI visibility feed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.services.growth.ai_visibility_design_handoff import (  # noqa: E402
    ai_agent_payments_design_handoff,
)
from server.services.growth.ai_visibility_docs_blueprint import (  # noqa: E402
    ai_agent_payments_docs_blueprint,
)
from server.services.growth.ai_visibility_plan import (  # noqa: E402
    ai_visibility_feed_packages,
    ai_visibility_optimization_plan,
)


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Export an executable Markdown brief for an AI visibility feed."
    )
    parser.add_argument("--feed-key", default="mcp_paid_api_discovery")
    parser.add_argument("--cycle-summary", help="Optional cycle summary JSON.")
    parser.add_argument(
        "--output", help="Write Markdown to this path instead of stdout."
    )
    args = parser.parse_args()

    brief = render_operator_brief(
        feed_key=args.feed_key,
        cycle_summary_path=args.cycle_summary or "",
    )
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(brief, encoding="utf-8")
    else:
        print(brief, end="")
    return 0


def render_operator_brief(*, feed_key: str, cycle_summary_path: str = "") -> str:
    plan = ai_visibility_optimization_plan()
    packages = ai_visibility_feed_packages(feed_key=feed_key).items
    if not packages:
        raise ValueError(f"unknown feed key: {feed_key}")
    package = packages[0]
    docs = ai_agent_payments_docs_blueprint()
    handoff = ai_agent_payments_design_handoff()
    cycle_summary = _read_json(cycle_summary_path) if cycle_summary_path else {}
    lines = [
        f"# AI Visibility Operator Brief: {package.feed_key}",
        "",
        f"Objective: {package.objective}",
        "",
        f"Canonical homepage: {plan.canonical_domain}",
        f"Docs category: {docs.category}",
        f"Figma file: {handoff.figma_file_name}",
        "",
        "## Current Gate",
        "",
    ]
    lines.extend(
        _bullets(cycle_summary.get("blockers") or ["Run feed validation first."])
    )
    lines.extend(_observed_outcome_section(cycle_summary))
    lines.extend(
        [
            "",
            "## Feed Surfaces",
            "",
        ]
    )
    lines.extend(_asset_sections(package.publish_assets))
    lines.extend(["## Product Docs Design", ""])
    lines.extend(_page_sections(docs.pages[:4]))
    lines.extend(
        ["## Stitch To Figma", "", f"Stitch prompt: {handoff.stitch_prompt}", ""]
    )
    lines.extend(_frame_sections(handoff.frames))
    lines.extend(
        [
            "## Platform Probe Strategy",
            "",
        ]
    )
    for strategy in package.platform_strategies:
        lines.extend(
            [
                f"### {strategy.platform}",
                "",
                f"Focus: {strategy.feed_focus}",
                "",
                f"Preferred surfaces: {', '.join(strategy.preferred_surfaces)}",
                "",
                f"Success signal: {strategy.success_signal}",
                "",
                f"Fallback action: {strategy.fallback_action}",
                "",
            ]
        )
    commands = cycle_summary.get("commands") or {}
    lines.extend(["## Execution Commands", ""])
    for label, command in _execution_commands(package, commands):
        lines.extend([f"### {label}", "", f"```bash\n{command}\n```", ""])
    lines.extend(["## Success Criteria", ""])
    lines.extend(_bullets(package.success_metrics))
    lines.extend(["", "## Next Actions", ""])
    lines.extend(_bullets(cycle_summary.get("next_actions") or package.next_actions))
    return "\n".join(lines).rstrip() + "\n"


def _asset_sections(assets) -> list[str]:
    lines: list[str] = []
    for asset in assets:
        lines.extend(
            [
                f"### {asset.surface}",
                "",
                f"Target: {asset.target}",
                "",
                f"Purpose: {asset.purpose}",
                "",
                "Validation:",
                "",
                f"```bash\n{asset.validation}\n```",
                "",
            ]
        )
    return lines


def _page_sections(pages) -> list[str]:
    lines: list[str] = []
    for page in pages:
        lines.extend(
            [
                f"### {page.title}",
                "",
                f"Canonical URL: {page.canonical_url}",
                "",
                f"Definition block: {page.definition_block}",
                "",
                f"Target queries: {', '.join(page.target_queries)}",
                "",
            ]
        )
    return lines


def _frame_sections(frames) -> list[str]:
    lines: list[str] = []
    for frame in frames:
        lines.extend(
            [
                f"### {frame.name}",
                "",
                f"Purpose: {frame.purpose}",
                "",
                "Prompt:",
                "",
                f"```text\n{frame.stitch_prompt}\n```",
                "",
            ]
        )
    return lines


def _execution_commands(package, commands: dict[str, Any]) -> list[tuple[str, str]]:
    api_readiness = str(
        commands.get("api_readiness")
        or _api_probe_command(package.feed_key, execute=False)
    )
    values = [
        (
            "Feed validation",
            commands.get("feed_validation") or package.validation_commands[0],
        ),
        (
            "Manual probe template",
            commands.get("manual_probe_template") or package.probe_template_command,
        ),
        ("API readiness", api_readiness),
        ("API execute", commands.get("api_execute") or _with_execute(api_readiness)),
        (
            "Record evidence",
            commands.get("record_evidence")
            or "python scripts/growth/record_ai_visibility_probe.py <probe.jsonl> --apply",
        ),
        (
            "Import public web search snapshot",
            commands.get("public_web_search_import")
            or (
                "python scripts/growth/import_ai_visibility_public_search_snapshot.py "
                "<public-web-search-snapshot.json> --output <public-web-search.jsonl>"
            ),
        ),
        (
            "Compare",
            commands.get("compare")
            or "curl -fsS 'http://localhost:9700/api/growth/ai-visibility/comparisons' | python -m json.tool",
        ),
    ]
    return [(label, str(command)) for label, command in values if str(command).strip()]


def _observed_outcome_section(cycle_summary: dict[str, Any]) -> list[str]:
    lines: list[str] = ["", "## Observed Search Outcome", ""]
    platform_results = cycle_summary.get("platform_results")
    if isinstance(platform_results, list) and platform_results:
        for result in platform_results:
            if not isinstance(result, dict):
                continue
            lines.append(
                "- "
                f"{result.get('platform', 'unknown')}: "
                f"{result.get('status', 'unknown')} "
                f"({result.get('mentioned_count', 0)} mentions / "
                f"{result.get('cited_count', 0)} citations). "
                f"Next: {result.get('next_action', '')}"
            )
    else:
        lines.append("- No platform-level probe outcome has been summarized yet.")
    lines.extend(["", "## Next Feed Targets", ""])
    source_hosts = cycle_summary.get("top_source_hosts")
    if isinstance(source_hosts, list) and source_hosts:
        for item in source_hosts[:8]:
            if not isinstance(item, dict):
                continue
            surface = item.get("surface") or item.get("value") or "unknown"
            lines.append(
                "- "
                f"{surface}: {item.get('value', '')} "
                f"appeared {item.get('count', 0)} time(s)."
            )
    else:
        lines.append("- No answer-engine source hosts have been summarized yet.")
    competitors = cycle_summary.get("top_competitors")
    if isinstance(competitors, list) and competitors:
        lines.extend(["", "Top competing/collision terms:"])
        for item in competitors[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('value', '')}: {item.get('count', 0)}")
    return lines


def _api_probe_command(feed_key: str, *, execute: bool) -> str:
    command = (
        "python scripts/growth/run_ai_visibility_api_probe.py "
        f"--feed-key {feed_key} "
        "--run-group YYYY-MM-DD-weekly "
        "--platforms chatgpt,claude,grok,gemini"
    )
    return f"{command} --execute" if execute else command


def _with_execute(command: str) -> str:
    return command if " --execute" in command else f"{command} --execute"


def _read_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items if str(item).strip()]


if __name__ == "__main__":
    raise SystemExit(main())
