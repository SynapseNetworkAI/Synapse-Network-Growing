"""Latest source-host live evidence scanner."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from server.services.growth.ai_visibility_source_host_surfaces import (
    source_host_surface,
)
from server.services.growth.ai_visibility_text import unique_strings

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class LatestLiveEvidence:
    status: str = ""
    missing_terms: list[str] = field(default_factory=list)
    source_url: str = ""
    validation_summary: str = ""


def latest_live_evidence(host: str) -> LatestLiveEvidence:
    surface = source_host_surface(host)
    root = PROJECT_ROOT / "docs/archive/evidence/growth/ai-visibility"
    candidates = list(_live_evidence_candidates(root, surface=surface))
    if not candidates:
        return LatestLiveEvidence()
    latest = max(candidates, key=lambda candidate: candidate[:2])
    return _latest_live_evidence_from_payload(latest[2])


def _live_evidence_candidates(
    root: Path, *, surface: str
) -> list[tuple[datetime, str, dict[str, object]]]:
    if not root.exists():
        return []
    candidates = []
    for path in sorted(root.glob("*.json")):
        payload = _read_json(path)
        if _is_live_evidence_payload(payload, surface=surface):
            candidates.append((_evidence_timestamp(payload), path.name, payload))
    return candidates


def _is_live_evidence_payload(payload: dict[str, object], *, surface: str) -> bool:
    status = str(payload.get("status") or "")
    return (
        payload.get("module_key") == "ai_visibility_source_host_execution"
        and str(payload.get("surface") or "") == surface
        and status in {"live_verified", "missing_required_terms"}
    )


def _latest_live_evidence_from_payload(
    payload: dict[str, object],
) -> LatestLiveEvidence:
    return LatestLiveEvidence(
        status=str(payload.get("status") or ""),
        missing_terms=unique_strings(
            [str(item) for item in payload.get("missing_terms", []) or []]
        ),
        source_url=str(payload.get("source_url") or ""),
        validation_summary=str(payload.get("validation_summary") or ""),
    )


def _read_json(path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _evidence_timestamp(payload: dict[str, object]) -> datetime:
    value = str(payload.get("checked_at") or payload.get("verified_at") or "").strip()
    if not value:
        return datetime.min.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
