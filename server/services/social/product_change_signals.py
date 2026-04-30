"""Public-safe product change signals for social content planning."""

from __future__ import annotations

import re
import shutil

# Bounded read-only git metadata for public-safe content signals.
import subprocess  # nosec B404
from pathlib import Path

from sqlalchemy.orm import Session

from server.database import (
    DeploymentRecordRow,
    ProjectPolicyRow,
    ReleaseTaskRow,
    RequirementRow,
    WorkflowRunRow,
)
from server.services.social import publishing

PRODUCT_CHANGE_SIGNAL_LIMIT = 8


def public_safe_signal(value: str | None, *, max_chars: int = 180) -> str:
    text = str(value or "").strip()
    text = re.sub(r"/(?:Users|home|workspace|tmp)/[A-Za-z0-9._/\-]*", "[path]", text)
    text = re.sub(
        r"\b(?:api[_-]?key|authorization|bearer|token|secret)\b[^\s,;)]*",
        "[redacted]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(?:ops|codex|bugfix|feature|release)/[A-Za-z0-9._/\-]+",
        "[internal branch]",
        text,
    )
    text = re.sub(r"\s+", " ", text)
    return publishing._bounded_excerpt(text, max_chars=max_chars)


def _active_project_policies(db: Session) -> list[ProjectPolicyRow]:
    return (
        db.query(ProjectPolicyRow)
        .filter(ProjectPolicyRow.status == "active")
        .order_by(ProjectPolicyRow.updated_at.desc(), ProjectPolicyRow.id.asc())
        .limit(5)
        .all()
    )


def _git_log_subjects(git_bin: str, root: Path) -> list[str]:
    try:
        # No shell; fixed git args; bounded timeout.
        result = subprocess.run(  # nosec B603
            [
                git_bin,
                "-C",
                str(root),
                "log",
                "--since=7 days ago",
                "--pretty=%s",
                "--max-count=2",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _git_signal_lines(policy: ProjectPolicyRow, git_bin: str) -> list[str]:
    root = Path(str(policy.root_path or ""))
    if not root.exists() or not (root / ".git").exists():
        return []
    signals: list[str] = []
    for line in _git_log_subjects(git_bin, root):
        cleaned = public_safe_signal(line)
        if cleaned:
            signals.append(f"{policy.display_name}: recent repo change - {cleaned}")
    return signals


def recent_git_change_signals(db: Session, *, limit: int = 3) -> list[str]:
    signals: list[str] = []
    git_bin = shutil.which("git")
    if not git_bin:
        return signals
    for policy in _active_project_policies(db):
        signals.extend(_git_signal_lines(policy, git_bin))
        if len(signals) >= limit:
            return signals[:limit]
    return signals


def _requirement_signals(db: Session) -> list[str]:
    requirements = (
        db.query(RequirementRow)
        .filter(
            RequirementRow.status.in_(
                ["completed", "done", "delivery_ready", "ready_for_merge"]
            )
        )
        .order_by(RequirementRow.updated_at.desc(), RequirementRow.id.desc())
        .limit(4)
        .all()
    )
    signals: list[str] = []
    for row in requirements:
        project = row.project_display_name or row.project_key or "Synapse product"
        signals.append(
            f"{project}: requirement delivered - {public_safe_signal(row.title)}"
        )
    return signals


def _deployment_signals(db: Session) -> list[str]:
    deployments = (
        db.query(DeploymentRecordRow)
        .filter(DeploymentRecordRow.status == "succeeded")
        .order_by(
            DeploymentRecordRow.finished_at.desc().nullslast(),
            DeploymentRecordRow.id.desc(),
        )
        .limit(4)
        .all()
    )
    signals: list[str] = []
    for row in deployments:
        project = row.project_key or "Synapse product"
        metadata = publishing._json_loads(row.metadata_json, {})
        service = metadata.get("service_key") or row.action or "service"
        note = public_safe_signal(
            row.notes or f"{service} deployed to {row.environment}"
        )
        signals.append(f"{project}: verified {row.environment} deployment - {note}")
    return signals


def _release_signals(db: Session) -> list[str]:
    releases = (
        db.query(ReleaseTaskRow)
        .filter(ReleaseTaskRow.status == "completed")
        .order_by(ReleaseTaskRow.updated_at.desc(), ReleaseTaskRow.id.desc())
        .limit(3)
        .all()
    )
    signals: list[str] = []
    for row in releases:
        project = row.project_display_name or row.project_key or "Synapse product"
        service = row.service_key or "service"
        signals.append(
            f"{project}: release completed for {service} on {row.environment}"
        )
    return signals


def _workflow_signals(db: Session) -> list[str]:
    workflows = (
        db.query(WorkflowRunRow)
        .filter(WorkflowRunRow.status.in_(["completed", "done"]))
        .order_by(
            WorkflowRunRow.completed_at.desc().nullslast(), WorkflowRunRow.id.desc()
        )
        .limit(3)
        .all()
    )
    signals: list[str] = []
    for row in workflows:
        signals.append(
            f"Ops workflow: {row.workflow_key} completed for goal {row.goal_key or 'current goal'}"
        )
    return signals


def _dedupe_signals(signals: list[str], *, limit: int) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for signal in signals:
        cleaned = public_safe_signal(signal, max_chars=220)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        unique.append(cleaned)
        if len(unique) >= limit:
            break
    return unique


def recent_product_change_signals(
    db: Session, *, limit: int = PRODUCT_CHANGE_SIGNAL_LIMIT
) -> list[str]:
    signals = [
        *_requirement_signals(db),
        *_deployment_signals(db),
        *_release_signals(db),
        *_workflow_signals(db),
        *recent_git_change_signals(db, limit=3),
    ]
    return _dedupe_signals(signals, limit=limit)


def planner_product_change_lines(signals: list[str]) -> str:
    return (
        "\n".join(f"- {signal}" for signal in signals)
        or "- no verified product-change signal yet; focus on evergreen product value."
    )
