"""AI visibility operator handoff bundle composition."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from server.services.growth.ai_visibility_brief import (
    ai_visibility_optimization_brief,
)
from server.services.growth.ai_visibility_external_probe_gate import (
    ai_visibility_external_probe_gate,
)
from server.services.growth.ai_visibility_goal_audit import (
    ai_visibility_goal_audit,
)
from server.services.growth.ai_visibility_live_readiness import (
    ai_visibility_live_readiness,
)
from server.services.growth.ai_visibility_discovery import ai_visibility_next_cycle
from server.services.growth.ai_visibility_release_snapshot import build_snapshot
from server.services.growth.ai_visibility_release_unblock import (
    DEFAULT_ACTOR,
    DEFAULT_TARGET_COMMIT,
)
from server.services.growth.ai_visibility_text import unique_strings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FEED_KEY = "mcp_paid_api_discovery"


def build_handoff_payloads(
    *,
    feed_key: str = DEFAULT_FEED_KEY,
    run_group: str = "",
    target_commit: str = DEFAULT_TARGET_COMMIT,
    actor: str = DEFAULT_ACTOR,
    output_dir: Path | None = None,
    db,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(UTC)
    safe_feed_key = (feed_key or DEFAULT_FEED_KEY).strip()
    safe_run_group = run_group or (
        f"{generated_at.date().isoformat()}-{safe_feed_key}-operator-handoff"
    )
    safe_output_dir = output_dir or Path(_default_output_dir(safe_run_group))
    release_snapshot = build_snapshot(
        target_commit=target_commit,
        actor=actor,
        feed_key=safe_feed_key,
        run_group=f"{safe_run_group}-release-snapshot",
    )
    live_readiness = _dump(
        ai_visibility_live_readiness(
            feed_keys=[safe_feed_key],
            run_group=f"{safe_run_group}-live-readiness",
        )
    )
    external_gate = _dump(
        ai_visibility_external_probe_gate(
            feed_key=safe_feed_key,
            run_group=f"{safe_run_group}-external-probe",
        )
    )
    optimization_brief = ai_visibility_optimization_brief(
        db,
        run_group=f"{safe_run_group}-operator-brief",
    )
    next_cycle = _dump(ai_visibility_next_cycle(db))
    goal_audit = _dump(
        ai_visibility_goal_audit(
            db,
            live_readiness=live_readiness,
            external_gate=external_gate,
        )
    )
    files = _files(safe_output_dir)
    manifest = build_handoff_manifest(
        generated_at=generated_at,
        output_dir=safe_output_dir,
        feed_key=safe_feed_key,
        run_group=safe_run_group,
        target_commit=target_commit,
        release_snapshot=release_snapshot,
        live_readiness=live_readiness,
        external_gate=external_gate,
        next_cycle=next_cycle,
        goal_audit=goal_audit,
        files=files,
    )
    return {
        "manifest": manifest,
        "release_snapshot": release_snapshot,
        "live_readiness": live_readiness,
        "external_probe_gate": external_gate,
        "next_cycle": next_cycle,
        "goal_audit": goal_audit,
        "operator_brief": optimization_brief.markdown,
        "files": files,
    }


def build_handoff_manifest(
    *,
    generated_at: datetime,
    output_dir: Path,
    feed_key: str,
    run_group: str,
    target_commit: str,
    release_snapshot: dict[str, Any],
    live_readiness: dict[str, Any],
    external_gate: dict[str, Any],
    next_cycle: dict[str, Any],
    goal_audit: dict[str, Any],
    files: dict[str, Path],
) -> dict[str, Any]:
    return {
        "module_key": "ai_visibility",
        "bundle_type": "operator_handoff",
        "generated_at": generated_at.isoformat(),
        "feed_key": feed_key,
        "run_group": run_group,
        "target_commit_sha": target_commit,
        "official_homepage": "https://www.synapse-network.ai/",
        "status": _handoff_status(
            release_snapshot=release_snapshot,
            live_readiness=live_readiness,
            external_gate=external_gate,
        ),
        "release_status": release_snapshot.get("status", "unknown"),
        "live_readiness_status": live_readiness.get("status", "unknown"),
        "external_probe_gate_status": external_gate.get("status", "unknown"),
        "goal_audit_status": goal_audit.get("status", "unknown"),
        "goal_achieved": bool(goal_audit.get("goal_achieved")),
        "ready_platforms": external_gate.get("ready_platforms") or [],
        "missing_platforms": external_gate.get("missing_platforms") or [],
        "blockers": _handoff_blockers(
            release_snapshot=release_snapshot,
            live_readiness=live_readiness,
            external_gate=external_gate,
            goal_audit=goal_audit,
        ),
        "next_actions": _handoff_next_actions(release_snapshot),
        "files": {key: _display_path(path) for key, path in files.items()},
        "commands": _handoff_commands(
            feed_key=feed_key,
            run_group=run_group,
            target_commit=target_commit,
            output_dir=output_dir,
            live_readiness=live_readiness,
            external_gate=external_gate,
            next_cycle=next_cycle,
            goal_audit=goal_audit,
        ),
    }


def _handoff_status(
    *,
    release_snapshot: dict[str, Any],
    live_readiness: dict[str, Any],
    external_gate: dict[str, Any],
) -> str:
    live_ready = live_readiness.get("status") != "blocked"
    if (
        release_snapshot.get("status") == "ready_for_release_runner"
        and live_ready
        and external_gate.get("ready_to_execute")
    ):
        return "ready_for_full_external_probes"
    if live_ready and external_gate.get("partial_ready_to_execute"):
        return "ready_for_partial_external_probes"
    return "blocked"


def _handoff_blockers(
    *,
    release_snapshot: dict[str, Any],
    live_readiness: dict[str, Any],
    external_gate: dict[str, Any],
    goal_audit: dict[str, Any],
) -> list[str]:
    live_blockers = [
        blocker
        for item in live_readiness.get("items") or []
        for blocker in item.get("missing_facts") or []
    ]
    return unique_strings(
        list(release_snapshot.get("blockers") or [])
        + live_blockers
        + list(external_gate.get("blockers") or [])
        + list(goal_audit.get("blockers") or [])
    )


def _handoff_next_actions(release_snapshot: dict[str, Any]) -> list[str]:
    return unique_strings(
        list(release_snapshot.get("next_actions") or [])
        + [
            "Run full GPT/Claude/Grok/Gemini probes only after production feed validation passes.",
        ]
    )


def _handoff_commands(
    *,
    feed_key: str,
    run_group: str,
    target_commit: str,
    output_dir: Path,
    live_readiness: dict[str, Any],
    external_gate: dict[str, Any],
    next_cycle: dict[str, Any],
    goal_audit: dict[str, Any],
) -> dict[str, str]:
    return {
        "rerun_handoff": (
            "python scripts/growth/generate_ai_visibility_handoff_bundle.py "
            f"--feed-key {feed_key} --run-group {run_group} "
            f"--target-commit {target_commit} --output-dir {output_dir}"
        ),
        "feed_validation": live_readiness.get("validation_command", ""),
        "record_readiness": live_readiness.get("apply_command", ""),
        "external_probe_gate": next_cycle.get("external_probe_gate_command", ""),
        "api_readiness": external_gate.get("api_readiness_command", ""),
        "partial_api_readiness": external_gate.get(
            "partial_api_readiness_command",
            "",
        ),
        "api_execute": external_gate.get("api_execute_command", ""),
        "record_probe": external_gate.get("record_probe_command", ""),
        "probe_matrix": next_cycle.get("probe_matrix_command", ""),
        "validate_matrix": next_cycle.get("validate_matrix_command", ""),
        "cycle_summary": next_cycle.get("cycle_summary_command", ""),
        "operator_brief": next_cycle.get("operator_brief_command", ""),
        "goal_audit": next_cycle.get("goal_audit_command")
        or goal_audit.get("export_command", ""),
        "compare": external_gate.get("compare_command", ""),
        "weekly_report": next_cycle.get("weekly_report_command", ""),
    }


def _files(output_dir: Path) -> dict[str, Path]:
    return {
        "release_snapshot": output_dir / "release-snapshot.json",
        "live_readiness": output_dir / "live-readiness.json",
        "external_probe_gate": output_dir / "external-probe-gate.json",
        "next_cycle": output_dir / "next-cycle.json",
        "goal_audit": output_dir / "goal-audit.json",
        "operator_brief": output_dir / "operator-brief.md",
        "manifest": output_dir / "manifest.json",
    }


def _default_output_dir(run_group: str) -> str:
    return f"docs/archive/evidence/growth/ai-visibility/{run_group}-handoff"


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _dump(value) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return dict(value)
