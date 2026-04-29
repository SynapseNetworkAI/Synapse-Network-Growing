"""Public-preview traction proof projection for Mission Board."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from server.database import ReleaseTaskRow, RequirementRow, SocialPostDraftRow
from server.services.planning.mission_board_helpers import (
    ACTIVE_REQUIREMENT_STATUSES,
    TERMINAL_REQUIREMENT_STATUSES,
)
from server.services.result_objects import ServiceObjectResult, service_object_result


def _proof_item(
    *,
    key: str,
    label: str,
    status: str,
    evidence_label: str,
    next_action: str,
    deep_link: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "evidence_label": evidence_label,
        "next_action": next_action,
        "deep_link": deep_link,
    }


def _published_x_count(db: Session) -> int:
    return (
        db.query(SocialPostDraftRow)
        .filter(SocialPostDraftRow.status == "published")
        .count()
    )


def _successful_release_count(db: Session) -> int:
    return db.query(ReleaseTaskRow).filter(ReleaseTaskRow.status == "completed").count()


def _provider_release_count(db: Session) -> int:
    return (
        db.query(ReleaseTaskRow)
        .filter(
            ReleaseTaskRow.status == "completed",
            ReleaseTaskRow.project_key == "synapse-network-provider",
        )
        .count()
    )


def _sdk_work_count(db: Session, *, manifest_id: int, goal_key: str | None) -> int:
    if not goal_key:
        return 0
    return (
        db.query(RequirementRow)
        .filter(
            RequirementRow.operating_manifest_id == manifest_id,
            RequirementRow.goal_key == goal_key,
            RequirementRow.project_key.in_(["synapse-network-sdk", "synapse-network"]),
            RequirementRow.status.in_(
                sorted(ACTIVE_REQUIREMENT_STATUSES | TERMINAL_REQUIREMENT_STATUSES)
            ),
        )
        .count()
    )


def _overall_status(items: list[dict[str, Any]]) -> str:
    statuses = {str(item["status"]) for item in items}
    if "blocked" in statuses:
        return "blocked"
    if "missing" in statuses:
        return "incomplete"
    return "present"


@service_object_result
def active_goal_traction_proof(
    db: Session,
    *,
    manifest_id: int,
    goal_key: str | None,
    lanes: dict[str, list[dict[str, Any]]],
    unassigned_items: list[dict[str, Any]],
) -> ServiceObjectResult:
    """Project public-preview traction proof without inventing green states."""

    published_x_count = _published_x_count(db)
    successful_release_count = _successful_release_count(db)
    provider_release_count = _provider_release_count(db)
    active_sdk_work_count = _sdk_work_count(
        db, manifest_id=manifest_id, goal_key=goal_key
    )

    items = [
        _proof_item(
            key="docs_staging_visits",
            label="Docs / staging visits",
            status="missing",
            evidence_label="analytics_unavailable",
            next_action="Connect docs/staging analytics or add an evidence source before claiming traffic proof.",
            deep_link="/planning?tab=opportunities",
        ),
        _proof_item(
            key="provider_onboarding",
            label="Provider onboarding proof",
            status="present" if provider_release_count else "missing",
            evidence_label=f"{provider_release_count} provider release(s)",
            next_action="Ship or verify Provider self-serve onboarding evidence.",
            deep_link="/releases",
        ),
        _proof_item(
            key="sdk_demo_completion",
            label="SDK demo completion",
            status="present" if active_sdk_work_count else "missing",
            evidence_label=f"{active_sdk_work_count} SDK-related work item(s)",
            next_action="Create or complete the SDK quickstart / agent demo requirement.",
            deep_link="/planning?tab=engineering",
        ),
        _proof_item(
            key="x_engagement",
            label="X engagement proof",
            status="present" if published_x_count else "missing",
            evidence_label=f"{published_x_count} published X post(s)",
            next_action="Review Social Ops drafts, replies, reposts, and published effects.",
            deep_link="/publishing",
        ),
        _proof_item(
            key="staging_release",
            label="Staging release proof",
            status="present" if successful_release_count else "missing",
            evidence_label=f"{successful_release_count} completed release task(s)",
            next_action="Publish eligible staging tasks and verify online records.",
            deep_link="/releases",
        ),
        _proof_item(
            key="ops_lane_health",
            label="Ops lane health",
            status="blocked" if unassigned_items else "present",
            evidence_label=(
                f"{len(unassigned_items)} unassigned item(s)"
                if unassigned_items
                else ", ".join(f"{key}:{len(value)}" for key, value in lanes.items())
            ),
            next_action="Repair unassigned lineage before trusting the mission board.",
            deep_link="/planning?tab=unassigned"
            if unassigned_items
            else "/command-center",
        ),
    ]
    return {"status": _overall_status(items), "items": items}
