"""Config-free source-host evidence facts for offline CLI handoffs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_DIR = PROJECT_ROOT / "docs/archive/evidence/growth/ai-visibility"


@dataclass(frozen=True)
class OfflineSourceHostAuditFacts:
    review_pending_surfaces: list[str] = field(default_factory=list)
    live_surfaces: list[str] = field(default_factory=list)


def offline_source_host_audit_facts(
    evidence_dir: str | Path = DEFAULT_EVIDENCE_DIR,
) -> OfflineSourceHostAuditFacts:
    root = Path(evidence_dir)
    if not root.exists():
        return OfflineSourceHostAuditFacts()
    review_pending: list[str] = []
    live: list[str] = []
    for path in sorted(root.glob("*.json")):
        payload = _read_json(path)
        if payload.get("module_key") != "ai_visibility_source_host_execution":
            continue
        surface = str(payload.get("surface") or "").strip()
        if not surface:
            continue
        if payload.get("status") == "live_verified":
            live.append(surface)
        if payload.get("status") == "submission_recorded" and _review_pending(payload):
            review_pending.append(surface)
    return OfflineSourceHostAuditFacts(
        review_pending_surfaces=_unique(review_pending),
        live_surfaces=_unique(live),
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
