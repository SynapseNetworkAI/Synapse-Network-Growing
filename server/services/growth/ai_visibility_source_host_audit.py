"""Fixed-scope source-host evidence loader for AI visibility goal audits."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from server.config import PROJECT_ROOT
from server.services.growth.ai_visibility_text import unique_strings

EVIDENCE_DIR = Path(PROJECT_ROOT) / "docs/archive/evidence/growth/ai-visibility"
REQUIRED_DIRECTORY_HOSTS = ("aitoolnet.com", "alternativeto.net")
SOURCE_HOST_FRAME = "Directory Source-Host Submission Pack"


@dataclass(frozen=True)
class SourceHostAuditFacts:
    checklist_hosts: list[str] = field(default_factory=list)
    framed_checklist_hosts: list[str] = field(default_factory=list)
    submission_command_hosts: list[str] = field(default_factory=list)
    submitted_surfaces: list[str] = field(default_factory=list)
    live_surfaces: list[str] = field(default_factory=list)
    evidence_files: list[str] = field(default_factory=list)

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
    submitted: list[str] = []
    live: list[str] = []
    evidence_files: list[str] = []

    for path in sorted(root.glob("*.json")):
        payload = _read_json(path)
        if not payload:
            continue
        if payload.get("checklist_type") == "source_host_feed_execution":
            _collect_checklist_hosts(
                payload,
                checklist_hosts=checklist_hosts,
                framed_hosts=framed_hosts,
                command_hosts=command_hosts,
                evidence_files=evidence_files,
                path=path,
            )
        if payload.get("module_key") == "ai_visibility_source_host_execution":
            _collect_execution_evidence(
                payload,
                submitted=submitted,
                live=live,
                evidence_files=evidence_files,
                path=path,
            )

    return SourceHostAuditFacts(
        checklist_hosts=unique_strings(checklist_hosts),
        framed_checklist_hosts=unique_strings(framed_hosts),
        submission_command_hosts=unique_strings(command_hosts),
        submitted_surfaces=unique_strings(submitted),
        live_surfaces=unique_strings(live),
        evidence_files=unique_strings(evidence_files),
    )


def merge_source_host_audit_facts(
    first: SourceHostAuditFacts,
    second: SourceHostAuditFacts,
) -> SourceHostAuditFacts:
    return SourceHostAuditFacts(
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
        live_surfaces=unique_strings(first.live_surfaces + second.live_surfaces),
        evidence_files=unique_strings(first.evidence_files + second.evidence_files),
    )


def source_host_checklist_facts(checklist: Any) -> SourceHostAuditFacts:
    checklist_hosts: list[str] = []
    framed_hosts: list[str] = []
    command_hosts: list[str] = []
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
    return SourceHostAuditFacts(
        checklist_hosts=unique_strings(checklist_hosts),
        framed_checklist_hosts=unique_strings(framed_hosts),
        submission_command_hosts=unique_strings(command_hosts),
    )


def missing_hosts(
    have: list[str],
    required: tuple[str, ...] = REQUIRED_DIRECTORY_HOSTS,
) -> list[str]:
    present = {_host_surface(item) for item in have}
    return [host for host in required if _host_surface(host) not in present]


def _collect_checklist_hosts(
    payload: dict[str, Any],
    *,
    checklist_hosts: list[str],
    framed_hosts: list[str],
    command_hosts: list[str],
    evidence_files: list[str],
    path: Path,
) -> None:
    matched = False
    for item in payload.get("items", []) or []:
        host = str(item.get("host") or "").strip()
        if not host:
            continue
        matched = True
        checklist_hosts.append(host)
        if str(item.get("design_handoff_frame") or "") == SOURCE_HOST_FRAME:
            framed_hosts.append(host)
        if "--evidence-mode submission-confirmation" in str(
            item.get("submission_confirmation_command") or ""
        ):
            command_hosts.append(host)
    if matched:
        evidence_files.append(_relative_evidence_path(path))


def _collect_execution_evidence(
    payload: dict[str, Any],
    *,
    submitted: list[str],
    live: list[str],
    evidence_files: list[str],
    path: Path,
) -> None:
    surface = str(payload.get("surface") or "").strip()
    if not surface:
        return
    if payload.get("status") == "submission_recorded":
        submitted.append(surface)
        evidence_files.append(_relative_evidence_path(path))
    if payload.get("status") == "live_verified":
        live.append(surface)
        evidence_files.append(_relative_evidence_path(path))


def _host_surface(value: str) -> str:
    host = value.strip().lower()
    if "." in host:
        return host.split(".", 1)[0].replace("-", "_")
    return host.replace("-", "_")


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
