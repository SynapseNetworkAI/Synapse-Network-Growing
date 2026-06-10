"""Fixed-scope source-host evidence loader for AI visibility goal audits."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from server.config import PROJECT_ROOT
from server.services.growth.ai_visibility_source_host_surfaces import (
    source_host_surface,
)
from server.services.growth.ai_visibility_text import unique_strings

EVIDENCE_DIR = Path(PROJECT_ROOT) / "docs/archive/evidence/growth/ai-visibility"
REQUIRED_DIRECTORY_HOSTS = ("aitoolnet.com", "alternativeto.net")
SOURCE_HOST_FRAME = "Directory Source-Host Submission Pack"


@dataclass(frozen=True)
class SourceHostAuditFacts:
    required_directory_hosts: list[str] = field(default_factory=list)
    checklist_hosts: list[str] = field(default_factory=list)
    framed_checklist_hosts: list[str] = field(default_factory=list)
    submission_command_hosts: list[str] = field(default_factory=list)
    submitted_surfaces: list[str] = field(default_factory=list)
    submission_blockers: list[str] = field(default_factory=list)
    review_pending_surfaces: list[str] = field(default_factory=list)
    live_surfaces: list[str] = field(default_factory=list)
    evidence_files: list[str] = field(default_factory=list)
    checklist_generated_at: datetime | None = None

    @property
    def submitted_or_live_surfaces(self) -> list[str]:
        return unique_strings(self.submitted_surfaces + self.live_surfaces)


def source_host_audit_facts(
    *,
    evidence_dir: Path | None = None,
) -> SourceHostAuditFacts:
    root = evidence_dir or EVIDENCE_DIR
    if not root.exists():
        return SourceHostAuditFacts()

    checklist_hosts: list[str] = []
    framed_hosts: list[str] = []
    command_hosts: list[str] = []
    required_hosts: list[str] = []
    submitted: list[str] = []
    blockers: list[str] = []
    review_pending: list[str] = []
    live: list[str] = []
    evidence_files: list[str] = []
    latest_checklist = _latest_checklist_payload(root)

    if latest_checklist:
        payload, path = latest_checklist
        _collect_checklist_hosts(
            payload,
            checklist_hosts=checklist_hosts,
            framed_hosts=framed_hosts,
            command_hosts=command_hosts,
            required_hosts=required_hosts,
            evidence_files=evidence_files,
            path=path,
        )

    for path in sorted(root.glob("*.json")):
        payload = _read_json(path)
        if not payload:
            continue
        if payload.get("module_key") == "ai_visibility_source_host_execution":
            _collect_execution_evidence(
                payload,
                submitted=submitted,
                blockers=blockers,
                review_pending=review_pending,
                live=live,
                evidence_files=evidence_files,
                path=path,
            )

    return SourceHostAuditFacts(
        required_directory_hosts=unique_strings(required_hosts),
        checklist_hosts=unique_strings(checklist_hosts),
        framed_checklist_hosts=unique_strings(framed_hosts),
        submission_command_hosts=unique_strings(command_hosts),
        submitted_surfaces=unique_strings(submitted),
        submission_blockers=unique_strings(blockers),
        review_pending_surfaces=unique_strings(review_pending),
        live_surfaces=unique_strings(live),
        evidence_files=unique_strings(evidence_files),
        checklist_generated_at=_generated_at(payload) if latest_checklist else None,
    )


def merge_source_host_audit_facts(
    first: SourceHostAuditFacts,
    second: SourceHostAuditFacts,
) -> SourceHostAuditFacts:
    newest = _newest_checklist_facts(first, second)
    required = newest.required_directory_hosts
    return SourceHostAuditFacts(
        required_directory_hosts=unique_strings(required),
        checklist_hosts=unique_strings(first.checklist_hosts + second.checklist_hosts),
        framed_checklist_hosts=unique_strings(
            first.framed_checklist_hosts + second.framed_checklist_hosts
        ),
        submission_command_hosts=unique_strings(
            first.submission_command_hosts + second.submission_command_hosts
        ),
        submitted_surfaces=unique_strings(
            first.submitted_surfaces + second.submitted_surfaces
        ),
        submission_blockers=unique_strings(
            first.submission_blockers + second.submission_blockers
        ),
        review_pending_surfaces=unique_strings(
            first.review_pending_surfaces + second.review_pending_surfaces
        ),
        live_surfaces=unique_strings(first.live_surfaces + second.live_surfaces),
        evidence_files=unique_strings(first.evidence_files + second.evidence_files),
        checklist_generated_at=newest.checklist_generated_at,
    )


def source_host_checklist_facts(checklist: Any) -> SourceHostAuditFacts:
    checklist_hosts: list[str] = []
    framed_hosts: list[str] = []
    command_hosts: list[str] = []
    required_hosts: list[str] = []
    for item in getattr(checklist, "items", []) or []:
        host = str(getattr(item, "host", "") or "").strip()
        if not host:
            continue
        checklist_hosts.append(host)
        if str(getattr(item, "design_handoff_frame", "") or "") == SOURCE_HOST_FRAME:
            framed_hosts.append(host)
        if "--evidence-mode submission-confirmation" in str(
            getattr(item, "submission_confirmation_command", "") or ""
        ):
            command_hosts.append(host)
            if _required_item_priority(getattr(item, "priority", 0)):
                required_hosts.append(host)
    return SourceHostAuditFacts(
        required_directory_hosts=unique_strings(required_hosts),
        checklist_hosts=unique_strings(checklist_hosts),
        framed_checklist_hosts=unique_strings(framed_hosts),
        submission_command_hosts=unique_strings(command_hosts),
    )


def missing_hosts(
    have: list[str],
    required: tuple[str, ...] | list[str] = REQUIRED_DIRECTORY_HOSTS,
) -> list[str]:
    present = {_host_surface(item) for item in have}
    return [host for host in required if _host_surface(host) not in present]


def _collect_checklist_hosts(
    payload: dict[str, Any],
    *,
    checklist_hosts: list[str],
    framed_hosts: list[str],
    command_hosts: list[str],
    required_hosts: list[str],
    evidence_files: list[str],
    path: Path,
) -> None:
    matched = False
    for item in payload.get("items", []) or []:
        host = _item_host(item)
        if not host:
            continue
        matched = True
        checklist_hosts.append(host)
        if _uses_source_host_frame(item):
            framed_hosts.append(host)
        if _has_submission_confirmation_command(item):
            command_hosts.append(host)
            if _required_item_priority(item.get("priority")):
                required_hosts.append(host)
    if matched:
        evidence_files.append(_relative_evidence_path(path))


def _latest_checklist_payload(root: Path) -> tuple[dict[str, Any], Path] | None:
    latest: tuple[datetime, str, dict[str, Any], Path] | None = None
    for path in sorted(root.glob("*.json")):
        payload = _read_json(path)
        if payload.get("checklist_type") == "source_host_feed_execution":
            candidate = (_generated_at(payload), path.name, payload, path)
            if latest is None or candidate[:2] > latest[:2]:
                latest = candidate
    if latest is None:
        return None
    return latest[2], latest[3]


def _item_host(item: dict[str, Any]) -> str:
    return str(item.get("host") or "").strip()


def _uses_source_host_frame(item: dict[str, Any]) -> bool:
    return str(item.get("design_handoff_frame") or "") == SOURCE_HOST_FRAME


def _has_submission_confirmation_command(item: dict[str, Any]) -> bool:
    return "--evidence-mode submission-confirmation" in str(
        item.get("submission_confirmation_command") or ""
    )


def _collect_execution_evidence(
    payload: dict[str, Any],
    *,
    submitted: list[str],
    blockers: list[str],
    review_pending: list[str],
    live: list[str],
    evidence_files: list[str],
    path: Path,
) -> None:
    surface = str(payload.get("surface") or "").strip()
    if not surface:
        return
    if payload.get("status") == "submission_recorded":
        submitted.append(surface)
        if _submission_is_review_pending(payload):
            review_pending.append(surface)
        evidence_files.append(_relative_evidence_path(path))
    if payload.get("status") == "submission_blocked":
        blockers.append(_submission_blocker_text(payload, surface))
        evidence_files.append(_relative_evidence_path(path))
    if payload.get("status") == "live_verified":
        live.append(surface)
        evidence_files.append(_relative_evidence_path(path))


def _submission_blocker_text(payload: dict[str, Any], surface: str) -> str:
    blocker = str(payload.get("blocker") or "").strip()
    next_action = str(payload.get("next_action") or "").strip()
    if blocker and next_action:
        return f"{surface}: {blocker} Next action: {next_action}"
    if blocker:
        return f"{surface}: {blocker}"
    return f"{surface}: submission was blocked; operator follow-up is required."


def _submission_is_review_pending(payload: dict[str, Any]) -> bool:
    evidence_text = " ".join(
        [
            str(payload.get("submitted_payload_summary") or ""),
            str(payload.get("validation_summary") or ""),
        ]
    ).casefold()
    review_markers = (
        "review it soon",
        "review your server",
        "submitted for review",
        "already been submitted",
        "publish it within",
    )
    return any(marker in evidence_text for marker in review_markers)


def _host_surface(value: str) -> str:
    return source_host_surface(value)


def _required_item_priority(value: object) -> bool:
    try:
        priority = int(value or 0)
    except (TypeError, ValueError):
        return False
    return 0 < priority <= 3


def _relative_evidence_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path(PROJECT_ROOT)))
    except ValueError:
        return str(path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _generated_at(payload: dict[str, Any]) -> datetime:
    value = str(payload.get("generated_at") or "").strip()
    if not value:
        return datetime.min.replace(tzinfo=UTC)
    try:
        return _normalized_datetime(
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        )
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)


def _newest_checklist_facts(
    first: SourceHostAuditFacts, second: SourceHostAuditFacts
) -> SourceHostAuditFacts:
    if not first.required_directory_hosts:
        return second
    if not second.required_directory_hosts:
        return first
    first_generated_at = first.checklist_generated_at or datetime.min.replace(
        tzinfo=UTC
    )
    second_generated_at = second.checklist_generated_at or datetime.min.replace(
        tzinfo=UTC
    )
    return first if first_generated_at >= second_generated_at else second


def _normalized_datetime(value: Any) -> datetime:
    if not isinstance(value, datetime):
        return datetime.min.replace(tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
