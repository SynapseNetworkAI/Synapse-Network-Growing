from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import RequirementRow

ACTIVE_FAMILY_REQUIREMENT_STATUSES = {
    "draft",
    "pending_approval",
    "approved",
    "planning",
    "plan_failed",
    "ready",
    "in_progress",
    "blocked",
    "paused",
    "needs_revision",
}

_STATUS_RANK = {
    "in_progress": 0,
    "blocked": 1,
    "paused": 2,
    "ready": 3,
    "planning": 4,
    "approved": 5,
    "pending_approval": 6,
    "draft": 7,
    "plan_failed": 8,
    "needs_revision": 9,
}

_VALIDATION_ROOT_MARKERS = (
    "/private/tmp/sng-delivery-",
    "sng-delivery-validation",
    "sng-delivery-autochain",
)


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _normalize_token(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"`+", "", text)
    text = re.sub(r"v\d+\b", "", text)
    text = re.sub(r"\breq(?:uirement)?[- ]?\d+\b", "", text)
    text = re.sub(r"\b#\d+\b", "", text)
    text = re.sub(r"\b[a-z]\b", "", text)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:96]


def _primary_target_root(target_project_path: str | None) -> str:
    for item in str(target_project_path or "").splitlines():
        item = item.strip()
        if item:
            return item
    return ""


def _is_validation_experiment(target_root: str, title: str, source_ref: str, source: str) -> bool:
    haystack = "\n".join([target_root, title, source_ref, source]).lower()
    return any(marker in haystack for marker in _VALIDATION_ROOT_MARKERS) and any(
        token in haystack
        for token in (
            "validation clone",
            "validation autochain",
            "queue chain",
            "branch delivery",
            "auto-start branch delivery",
            "live:auto-validation",
            "live:autochain",
            "live-validation:unattended-branch-delivery",
        )
    )


def _incident_code(title: str, source_ref: str, metadata: dict[str, Any]) -> str:
    for value in (
        metadata.get("incident_code"),
        metadata.get("incident_family"),
        source_ref,
        title,
    ):
        text = str(value or "").lower()
        match = re.search(
            r"(runtime_failure|bugfix_regression_failure|workflow_step_failure|stale_memory_blocked|automated_validation_failure|bugfix_circuit_breaker|manual_override(?:_load)?)",
            text,
        )
        if match:
            return _normalize_token(match.group(1))
    return ""


def build_requirement_family_context(
    *,
    title: str,
    source: str | None,
    source_ref: str | None,
    target_project_path: str | None,
    description_markdown: str | None = None,
    intake_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(intake_metadata or {})
    source_text = str(source or "manual").strip().lower() or "manual"
    source_ref_text = str(source_ref or "").strip()
    title_text = str(title or "").strip()
    description_text = str(description_markdown or "").strip()
    target_root = _primary_target_root(target_project_path)
    title_norm = _normalize_token(title_text)
    target_norm = _normalize_token(target_root or "org_ops")
    haystack = "\n".join([title_text, description_text, source_ref_text, source_text]).lower()

    category = "manual_requirement"
    key_suffix = title_norm or "requirement"

    if _is_validation_experiment(target_root, title_text, source_ref_text, source_text):
        category = "validation_experiment"
        if "queue chain" in haystack:
            key_suffix = "queue_chain"
        elif "autochain" in haystack:
            key_suffix = "autochain"
        else:
            key_suffix = "branch_delivery"
    elif title_text.lower().startswith("release bottleneck:") or "delivery blocker:" in haystack:
        category = "release_bottleneck"
        key_suffix = "release_gate"
    elif (
        source_text == "automation_candidate"
        or title_text.lower().startswith("approval automation:")
        or "manual override" in haystack
        or "approval_automation" in haystack
    ):
        category = "approval_automation"
        key_suffix = "manual_override"
    elif title_text.lower().startswith("incident recovery:") or "workflow incident:" in haystack:
        category = "incident_recovery"
        key_suffix = _incident_code(title_text, source_ref_text, metadata) or "incident"
    elif title_text.lower().startswith("bug fix:"):
        category = "bug_fix"
        key_suffix = (
            _normalize_token(str(metadata.get("bug_signature") or ""))
            or _normalize_token(str(metadata.get("bug_fingerprint") or ""))
            or _incident_code(title_text, source_ref_text, metadata)
            or title_norm
            or "bug"
        )
    elif title_text.lower().startswith("defect reduction:"):
        category = "defect_reduction"
        if " implementation" in haystack:
            key_suffix = "implementation"
        elif " bugfix" in haystack:
            key_suffix = "bugfix"
        else:
            key_suffix = title_norm or "defect"
    elif source_text == "bugfix_circuit_breaker" or source_ref_text.startswith("bugfix-circuit-breaker:"):
        category = "operator_followup"
        key_suffix = _normalize_token(source_ref_text) or "bugfix_circuit_breaker"

    family_key = f"{category}::{target_norm}::{key_suffix}"
    return {
        "family_key": family_key,
        "family_category": category,
        "family_target_root": target_root or None,
        "family_key_suffix": key_suffix,
        "is_validation_experiment": category == "validation_experiment",
    }


def requirement_family_context_for_requirement(requirement: RequirementRow) -> dict[str, Any]:
    intake = _json_loads(getattr(requirement, "intake_metadata_json", None), {})
    family_key = str((intake or {}).get("family_key") or "").strip()
    if family_key:
        return {
            "family_key": family_key,
            "family_category": str((intake or {}).get("family_category") or "manual_requirement"),
            "family_target_root": str((intake or {}).get("family_target_root") or "") or None,
            "family_key_suffix": str((intake or {}).get("family_key_suffix") or "") or None,
            "is_validation_experiment": bool((intake or {}).get("is_validation_experiment")),
        }
    return build_requirement_family_context(
        title=str(getattr(requirement, "title", "") or ""),
        source=str(getattr(requirement, "source", "") or ""),
        source_ref=str(getattr(requirement, "source_ref", "") or ""),
        target_project_path=str(getattr(requirement, "target_project_path", "") or ""),
        description_markdown=str(getattr(requirement, "description_markdown", "") or ""),
        intake_metadata=intake if isinstance(intake, dict) else {},
    )


def _canonical_requirement_sort_key(requirement: RequirementRow) -> tuple[int, int, float, int]:
    status = str(getattr(requirement, "status", "") or "")
    updated = getattr(requirement, "updated_at", None) or getattr(requirement, "created_at", None) or datetime.min.replace(tzinfo=timezone.utc)
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (
        _STATUS_RANK.get(status, 99),
        -int(getattr(requirement, "current_plan_version", 0) or 0),
        -float((updated - epoch).total_seconds()),
        -int(getattr(requirement, "id", 0) or 0),
    )


def find_active_requirement_for_family(
    db: Session,
    *,
    family_key: str,
    exclude_requirement_id: int | None = None,
) -> RequirementRow | None:
    rows = (
        db.query(RequirementRow)
        .filter(RequirementRow.status.in_(tuple(ACTIVE_FAMILY_REQUIREMENT_STATUSES)))
        .order_by(RequirementRow.id.desc())
        .all()
    )
    matches: list[RequirementRow] = []
    for row in rows:
        if exclude_requirement_id is not None and int(row.id) == int(exclude_requirement_id):
            continue
        context = requirement_family_context_for_requirement(row)
        if str(context.get("family_key") or "") == str(family_key):
            matches.append(row)
    if not matches:
        return None
    matches.sort(key=_canonical_requirement_sort_key)
    return matches[0]


def build_requirement_family_recommendation(
    *,
    title: str,
    source: str | None,
    source_ref: str | None,
    target_project_path: str | None,
    description_markdown: str | None = None,
    intake_metadata: dict[str, Any] | None = None,
    existing_requirement: RequirementRow | None = None,
) -> dict[str, Any]:
    context = build_requirement_family_context(
        title=title,
        source=source,
        source_ref=source_ref,
        target_project_path=target_project_path,
        description_markdown=description_markdown,
        intake_metadata=intake_metadata,
    )
    if existing_requirement is not None:
        action = "reuse_existing"
        reason = "agent recommendation keeps one active requirement per family"
        confidence = 0.92
        if bool(context.get("is_validation_experiment")):
            action = "archive_experiment"
            reason = "validation experiment family already has an active requirement; archive the duplicate experiment"
            confidence = 0.97
        return {
            "family_key": context["family_key"],
            "family_category": context["family_category"],
            "action": action,
            "confidence": confidence,
            "reason": reason,
            "primary_requirement_id": int(existing_requirement.id),
        }
    return {
        "family_key": context["family_key"],
        "family_category": context["family_category"],
        "action": "create_new",
        "confidence": 0.88,
        "reason": "no active requirement exists for this family",
        "primary_requirement_id": None,
    }


def cleanup_requirement_families(
    db: Session,
    *,
    categories: set[str] | None = None,
    archive_validation_experiments: bool = True,
) -> dict[str, Any]:
    rows = (
        db.query(RequirementRow)
        .filter(RequirementRow.status.in_(tuple(ACTIVE_FAMILY_REQUIREMENT_STATUSES)))
        .order_by(RequirementRow.id.desc())
        .all()
    )
    groups: dict[str, list[RequirementRow]] = {}
    contexts: dict[int, dict[str, Any]] = {}
    for row in rows:
        context = requirement_family_context_for_requirement(row)
        contexts[int(row.id)] = context
        category = str(context.get("family_category") or "")
        if categories and category not in categories:
            continue
        family_key = str(context.get("family_key") or "").strip()
        if not family_key:
            continue
        groups.setdefault(family_key, []).append(row)

    archived_requirement_ids: list[int] = []
    kept_requirement_ids: list[int] = []
    duplicate_groups: list[dict[str, Any]] = []
    visited: set[int] = set()

    from server.services.workflows.orchestrator import _create_artifact, _soft_delete_requirement_tree

    for family_key, members in groups.items():
        if len(members) <= 1:
            continue
        members.sort(key=_canonical_requirement_sort_key)
        canonical = members[0]
        canonical_id = int(canonical.id)
        context = contexts.get(canonical_id) or requirement_family_context_for_requirement(canonical)
        category = str(context.get("family_category") or "manual_requirement")
        duplicates = members[1:]
        recommendation = build_requirement_family_recommendation(
            title=str(canonical.title or ""),
            source=str(canonical.source or ""),
            source_ref=str(canonical.source_ref or ""),
            target_project_path=str(canonical.target_project_path or ""),
            description_markdown=str(canonical.description_markdown or ""),
            intake_metadata=_json_loads(getattr(canonical, "intake_metadata_json", None), {}),
            existing_requirement=canonical,
        )
        action = str(recommendation.get("action") or "reuse_existing")
        archived_ids_for_group: list[int] = []
        duplicate_ids = [int(row.id) for row in duplicates]
        if archive_validation_experiments and category == "validation_experiment":
            for duplicate in duplicates:
                duplicate_id = int(duplicate.id)
                duplicate_intake = _json_loads(getattr(duplicate, "intake_metadata_json", None), {})
                duplicate_intake.update(
                    {
                        "family_key": family_key,
                        "family_category": category,
                        "family_cleanup": {
                            "action": "archived_duplicate_experiment",
                            "primary_requirement_id": canonical_id,
                        },
                    }
                )
                duplicate.intake_metadata_json = json.dumps(duplicate_intake, ensure_ascii=False)
                _create_artifact(
                    db,
                    requirement_id=duplicate_id,
                    artifact_type="family_cleanup_decision",
                    content_summary=f"Archived duplicate family requirement #{duplicate_id}",
                    human_readable_body=(
                        f"Requirement family duplicate archived under primary requirement #{canonical_id}.\n"
                        f"Family key: `{family_key}`\n"
                        f"Reason: validation experiment duplicate"
                    ),
                    machine_readable_payload={
                        "family_key": family_key,
                        "family_category": category,
                        "primary_requirement_id": canonical_id,
                        "duplicate_requirement_id": duplicate_id,
                        "action": "archived_duplicate_experiment",
                    },
                )
                _soft_delete_requirement_tree(db, duplicate, visited)
                archived_requirement_ids.append(duplicate_id)
                archived_ids_for_group.append(duplicate_id)
            action = "archive_experiment"

        canonical_intake = _json_loads(getattr(canonical, "intake_metadata_json", None), {})
        canonical_intake.update(
            {
                "family_key": family_key,
                "family_category": category,
                "family_cleanup": {
                    "action": action,
                    "duplicate_requirement_ids": duplicate_ids,
                    "archived_requirement_ids": archived_ids_for_group,
                },
                "family_recommendation": {
                    **recommendation,
                    "action": action,
                    "primary_requirement_id": canonical_id,
                },
            }
        )
        canonical.intake_metadata_json = json.dumps(canonical_intake, ensure_ascii=False)
        _create_artifact(
            db,
            requirement_id=canonical_id,
            artifact_type="family_cleanup_decision",
            content_summary=f"Family cleanup decision for requirement #{canonical_id}",
            human_readable_body=(
                f"Family key: `{family_key}`\n"
                f"Category: `{category}`\n"
                f"Primary requirement: #{canonical_id}\n"
                f"Duplicate requirements: {', '.join(str(item) for item in duplicate_ids)}\n"
                f"Action: `{action}`"
            ),
            machine_readable_payload={
                "family_key": family_key,
                "family_category": category,
                "primary_requirement_id": canonical_id,
                "duplicate_requirement_ids": duplicate_ids,
                "archived_requirement_ids": archived_ids_for_group,
                "recommendation": {
                    **recommendation,
                    "action": action,
                    "primary_requirement_id": canonical_id,
                },
            },
        )
        kept_requirement_ids.append(canonical_id)
        duplicate_groups.append(
            {
                "family_key": family_key,
                "family_category": category,
                "primary_requirement_id": canonical_id,
                "duplicate_requirement_ids": duplicate_ids,
                "archived_requirement_ids": archived_ids_for_group,
                "recommended_action": action,
            }
        )

    db.commit()
    return {
        "family_count": len(groups),
        "duplicate_group_count": len(duplicate_groups),
        "kept_requirement_ids": sorted(set(kept_requirement_ids)),
        "archived_requirement_ids": sorted(set(archived_requirement_ids)),
        "duplicate_groups": duplicate_groups,
    }
