"""Nested mission board projection for Goal Mission Lanes."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from server.services.planning.lifecycle import ensure_active_manifest, goal_to_dict
from server.services.planning.mission_board_helpers import iso_timestamp, sort_mission_items
from server.services.planning.mission_lane_items import (
    growth_items,
    product_planner_items,
    software_items,
    unassigned_items,
)
from server.services.planning.product_opportunities import (
    ensure_product_opportunity_table,
)
from server.services.planning.traction_proof import active_goal_traction_proof

LANE_KEYS = ("product_planner", "growth_lead", "software_engineer")


def _goal_rows(db: Session, manifest_id: int):
    from server.database import PlanningGoalRow

    return (
        db.query(PlanningGoalRow)
        .filter(PlanningGoalRow.manifest_id == manifest_id)
        .order_by(PlanningGoalRow.status.asc(), PlanningGoalRow.id.asc())
        .all()
    )


def _active_goals(db: Session, manifest_id: int) -> list[dict[str, Any]]:
    return [
        goal_to_dict(row, include_intent=False)
        for row in _goal_rows(db, manifest_id)
        if str(row.status or "active") == "active"
    ]


def _primary_active_goal(goals: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not goals:
        return None
    for goal in goals:
        if str(goal.get("domain") or "") == "company":
            return goal
    return goals[0]


def _software_items_for_active_goals(
    db: Session, manifest_id: int, goals: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for goal in goals:
        goal_key = str(goal.get("goal_key") or "")
        if not goal_key:
            continue
        for item in software_items(db, manifest_id, goal_key):
            item_id = str(item.get("id") or "")
            if item_id in seen:
                continue
            seen.add(item_id)
            items.append(item)
    return sort_mission_items(items)


def _next_actions(
    lanes: dict[str, list[dict[str, Any]]],
    orphaned_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions = [_lane_next_action(key, lanes[key][0]) for key in LANE_KEYS if lanes[key]]
    if orphaned_items:
        actions.insert(
            0,
            {
                "lane": "unassigned",
                "title": f"{len(orphaned_items)} unassigned active item(s)",
                "next_action": "Open unassigned queue and repair lineage.",
                "deep_link": "/planning?tab=unassigned",
                "status": "blocked",
            },
        )
    return actions


def _lane_next_action(lane_key: str, first: dict[str, Any]) -> dict[str, Any]:
    return {
        "lane": lane_key,
        "title": first["title"],
        "next_action": first["next_action"],
        "deep_link": first["deep_link"],
        "status": first["status"],
    }


def mission_board_snapshot(db: Session) -> dict[str, Any]:
    ensure_product_opportunity_table(db)
    manifest = ensure_active_manifest(db)
    manifest_id = int(manifest.id)
    active_goals = _active_goals(db, manifest_id)
    active_goal = _primary_active_goal(active_goals)
    active_goal_key = str(active_goal.get("goal_key") or "") if active_goal else None
    lanes = {
        "product_planner": product_planner_items(db, manifest_id),
        "growth_lead": growth_items(db),
        "software_engineer": _software_items_for_active_goals(
            db, manifest_id, active_goals
        ),
    }
    orphaned_items = unassigned_items(db, manifest_id)
    traction_proof = active_goal_traction_proof(
        db,
        manifest_id=manifest_id,
        goal_key=active_goal_key,
        lanes=lanes,
        unassigned_items=orphaned_items,
    )
    return {
        "active_goal": active_goal,
        "active_goals": active_goals,
        "lanes": lanes,
        "lane_summary": {key: {"count": len(value)} for key, value in lanes.items()},
        "unassigned": {"count": len(orphaned_items), "items": orphaned_items},
        "traction_proof": traction_proof,
        "next_actions": _next_actions(lanes, orphaned_items),
        "manifest": {
            "id": manifest_id,
            "version_name": str(manifest.version_name or ""),
            "cycle_label": str(manifest.cycle_label or ""),
            "updated_at": iso_timestamp(manifest.updated_at),
        },
    }
