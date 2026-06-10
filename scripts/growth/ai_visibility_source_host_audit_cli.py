"""Config-free source-host evidence facts for offline CLI handoffs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from server.services.growth.ai_visibility_source_host_audit_events import (
    SurfaceEvent,
    _surface_statuses,
    append_live_surface_event,
    append_review_pending_surface_event,
    record_payload_surface_event,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_DIR = PROJECT_ROOT / "docs/archive/evidence/growth/ai-visibility"


@dataclass(frozen=True)
class OfflineSourceHostAuditFacts:
    review_pending_surfaces: list[str] = field(default_factory=list)
    metadata_refresh_surfaces: list[str] = field(default_factory=list)
    live_surfaces: list[str] = field(default_factory=list)
    surface_statuses: dict[str, str] = field(default_factory=dict)


def offline_source_host_audit_facts(
    evidence_dir: str | Path = DEFAULT_EVIDENCE_DIR,
) -> OfflineSourceHostAuditFacts:
    root = Path(evidence_dir)
    if not root.exists():
        return OfflineSourceHostAuditFacts()
    review_pending: list[str] = []
    metadata_refresh: list[str] = []
    live: list[str] = []
    surface_events: dict[str, SurfaceEvent] = {}
    for path in sorted(root.glob("*.json")):
        payload = _read_json(path)
        if payload.get("module_key") == "ai_visibility_source_host_execution":
            surface = str(payload.get("surface") or "").strip()
            if not surface:
                continue
            if payload.get("status") == "live_verified":
                append_live_surface_event(
                    live,
                    surface_events,
                    surface,
                    payload,
                    path,
                )
            if payload.get("status") == "submission_recorded" and _review_pending(
                payload
            ):
                append_review_pending_surface_event(
                    review_pending,
                    surface_events,
                    surface,
                    payload,
                    path,
                )
        if payload.get("check_type") == "source_host_live_spot_check":
            for item in payload.get("items", []) or []:
                if not isinstance(item, dict):
                    continue
                if item.get("status") != "candidate_incomplete":
                    continue
                host = str(item.get("host") or "").strip()
                if not host:
                    continue
                metadata_refresh.append(host)
                record_payload_surface_event(
                    surface_events,
                    host,
                    "metadata_refresh_required",
                    payload,
                    path,
                )
    return OfflineSourceHostAuditFacts(
        review_pending_surfaces=_unique(review_pending),
        metadata_refresh_surfaces=_unique(metadata_refresh),
        live_surfaces=_unique(live),
        surface_statuses=_surface_statuses(surface_events),
    )


def maybe_offline_source_host_audit_facts(
    enabled: bool,
) -> OfflineSourceHostAuditFacts | None:
    if not enabled:
        return None
    return offline_source_host_audit_facts()


def _review_pending(payload: dict[str, object]) -> bool:
    text = " ".join(
        [
            str(payload.get("submitted_payload_summary") or ""),
            str(payload.get("validation_summary") or ""),
        ]
    ).casefold()
    markers = (
        "review it soon",
        "review your server",
        "submitted for review",
        "already been submitted",
        "publish it within",
    )
    return any(marker in text for marker in markers)


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
