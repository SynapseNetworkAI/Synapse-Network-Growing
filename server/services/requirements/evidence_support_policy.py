from __future__ import annotations


def _command_mentions_any(command: str, needles: tuple[str, ...]) -> bool:
    lowered = str(command or "").lower()
    return any(needle in lowered for needle in needles)


def _has_supporting_command(commands: list[str], needles: tuple[str, ...]) -> bool:
    return any(_command_mentions_any(command, needles) for command in commands)


def _diff_or_code_delivery_supported(
    commands: list[str], expected_outcome: str
) -> bool:
    return expected_outcome == "code_delivery" or any(
        command in {"git diff --check", "git diff --stat"} for command in commands
    )


def required_evidence_support_error(
    evidence_type: str, commands: list[str], expected_outcome: str
) -> str | None:
    normalized = str(evidence_type or "").strip()
    if normalized in {"workflow_command_result", "workflow_agent_raw_output"}:
        return None
    command_requirements = {
        "frontend_validation_result": (
            ("npm ", "npm --prefix dashboard", "cd dashboard && npm"),
            "frontend_validation_result requires an npm/dashboard validation command.",
        ),
        "coverage_report": (
            ("diff-cover", "coverage.xml", "--cov"),
            "coverage_report requires a diff-cover, coverage.xml, or pytest --cov command.",
        ),
        "docs_sync_review": (
            ("agent_guardrails.sh", "docs", "doc_sync", "docs-sync", "docs drift"),
            "docs_sync_review requires a docs sync, docs drift, rg docs, or agent_guardrails command.",
        ),
    }
    if normalized in command_requirements:
        needles, message = command_requirements[normalized]
        return None if _has_supporting_command(commands, needles) else message
    if normalized in {"project_change_summary", "git_diff_summary"}:
        return (
            None
            if _diff_or_code_delivery_supported(commands, expected_outcome)
            else f"{normalized} requires code_delivery or git diff --check evidence."
        )
    return None
