"""Mission Workbench tree projection.

The workbench is intentionally a nested tree, not a graph. It is optimized for a
simple TreeGrid UI that can show Goal -> Lane -> Task -> Evidence without a
canvas/flow-layout dependency.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from server.services.planning.lifecycle import ensure_active_manifest
from server.services.planning.mission_board import (
    _active_goals,
    _primary_active_goal,
)
from server.services.planning.mission_board_helpers import iso_timestamp
from server.services.planning.mission_lane_items import (
    growth_items,
    product_planner_items,
    software_items,
    unassigned_items,
)
from server.services.planning.product_opportunities import (
    ensure_product_opportunity_table,
)
from server.services.result_objects import ServiceObjectResult, service_object_result

STAGES = (
    "opportunity",
    "candidate",
    "requirement",
    "workflow",
    "pr",
    "release",
    "online_record",
)
LANE_LABELS = {
    "product_planner": "Product Planner",
    "growth_lead": "Growth Lead",
    "software_engineer": "Software Engineer",
}


def _blank_stages() -> dict[str, str]:
    return {stage: "missing" for stage in STAGES}


def _stage_for_item_type(item_type: str) -> str:
    return {
        "product_opportunity": "opportunity",
        "publishing_draft": "opportunity",
        "reply_draft": "opportunity",
        "repost_candidate": "opportunity",
        "requirement_candidate": "candidate",
        "requirement": "requirement",
        "workflow": "workflow",
        "release_task": "release",
    }.get(item_type, "opportunity")


def _normalize_stage_status(status: str) -> str:
    value = str(status or "").lower()
    if value in {"failed", "blocked", "validation_failed"}:
        return "blocked"
    if value in {"running", "queued", "executing"}:
        return "running"
    if value in {"completed", "succeeded", "done", "published", "merged"}:
        return "completed"
    if value in {
        "pending",
        "proposed",
        "approved",
        "needs_review",
        "awaiting_operator",
        "candidate",
        "requested",
        "draft",
        "generating",
    }:
        return "waiting"
    if value in {"active", "ready", "materialized"}:
        return "active"
    return "missing"


def _aggregate_stage_status(values: list[str]) -> str:
    if any(value == "blocked" for value in values):
        return "blocked"
    if any(value == "running" for value in values):
        return "running"
    if any(value in {"waiting", "active"} for value in values):
        return "waiting"
    if any(value == "completed" for value in values):
        return "completed"
    return "missing"


def _aggregate_stages(children: list[dict[str, Any]]) -> dict[str, str]:
    stages = _blank_stages()
    for stage in STAGES:
        stages[stage] = _aggregate_stage_status(
            [
                str(child.get("stage_statuses", {}).get(stage) or "missing")
                for child in children
            ]
        )
    return stages


def _detail_api_for_item(item_id: str) -> str | None:
    prefix, _, raw_id = str(item_id).partition(":")
    if not raw_id:
        return None
    return {
        "product_opportunity": f"/api/planning/product-opportunities/{raw_id}",
        "candidate": f"/api/planning/candidates?candidate_id={raw_id}",
        "requirement": f"/api/requirements/{raw_id}",
        "workflow": f"/api/workflows/runs/{raw_id}",
        "release_task": "/api/releases/tasks",
        "social_draft": f"/api/social/posts/{raw_id}",
        "social_reply": "/api/social/replies",
        "social_repost": "/api/social/repost-candidates",
    }.get(prefix)


def _node(
    *,
    node_id: str,
    parent_id: str | None,
    level: int,
    node_type: str,
    title: str,
    status: str,
    lane: str | None = None,
    goal_key: str | None = None,
    next_action: str = "",
    deep_link: str | None = None,
    detail_api: str | None = None,
    updated_at: Any = None,
    stage_statuses: dict[str, str] | None = None,
    evidence_label: str = "",
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "parent_id": parent_id,
        "level": level,
        "type": node_type,
        "title": title,
        "status": status,
        "lane": lane,
        "goal_key": goal_key,
        "stage_statuses": stage_statuses or _blank_stages(),
        "next_action": next_action,
        "deep_link": deep_link,
        "detail_api": detail_api,
        "updated_at": iso_timestamp(updated_at),
        "evidence_label": evidence_label,
        "children": children or [],
    }


def _task_node(
    item: dict[str, Any], *, parent_id: str, level: int, lane: str, goal_key: str | None
) -> dict[str, Any]:
    stages = _blank_stages()
    stages[_stage_for_item_type(str(item.get("type") or ""))] = _normalize_stage_status(
        str(item.get("status") or "")
    )
    return _node(
        node_id=str(item.get("id") or ""),
        parent_id=parent_id,
        level=level,
        node_type=str(item.get("type") or "work_item"),
        title=str(item.get("title") or "Untitled work item"),
        status=str(item.get("status") or "unknown"),
        lane=lane,
        goal_key=goal_key,
        stage_statuses=stages,
        next_action=str(item.get("next_action") or ""),
        deep_link=item.get("deep_link"),
        detail_api=_detail_api_for_item(str(item.get("id") or "")),
        updated_at=item.get("updated_at"),
        evidence_label=str(item.get("evidence_label") or ""),
    )


def _lane_node(
    *,
    lane_key: str,
    parent_id: str,
    level: int,
    goal_key: str | None,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    children = [
        _task_node(
            item,
            parent_id=f"lane:{lane_key}:{goal_key or 'global'}",
            level=level + 1,
            lane=lane_key,
            goal_key=goal_key,
        )
        for item in items
    ]
    status = _aggregate_stage_status(
        [stage for child in children for stage in child["stage_statuses"].values()]
    )
    return _node(
        node_id=f"lane:{lane_key}:{goal_key or 'global'}",
        parent_id=parent_id,
        level=level,
        node_type="mission_lane",
        title=LANE_LABELS.get(lane_key, lane_key),
        status=status,
        lane=lane_key,
        goal_key=goal_key,
        stage_statuses=_aggregate_stages(children),
        next_action=_lane_next_action(lane_key, children),
        deep_link=_lane_deep_link(lane_key),
        children=children,
    )


def _lane_next_action(lane_key: str, children: list[dict[str, Any]]) -> str:
    if children:
        return str(children[0].get("next_action") or "Open lane work item.")
    return {
        "product_planner": "Review proposed opportunities or run product planner.",
        "growth_lead": "Open Publishing to review drafts, replies, and repost candidates.",
        "software_engineer": "Run Planner Sweep to generate evidence-bound engineering candidates.",
    }.get(lane_key, "Open lane.")


def _lane_deep_link(lane_key: str) -> str:
    return {
        "product_planner": "/planning?tab=opportunities",
        "growth_lead": "/publishing",
        "software_engineer": "/planning?tab=engineering",
    }.get(lane_key, "/planning")


def _goal_node(
    *,
    goal: dict[str, Any],
    parent_id: str,
    level: int,
    manifest_id: int,
    db: Session,
) -> dict[str, Any]:
    goal_key = str(goal.get("goal_key") or "")
    lane_children = [
        _lane_node(
            lane_key="software_engineer",
            parent_id=f"goal:{goal_key}",
            level=level + 1,
            goal_key=goal_key,
            items=software_items(db, manifest_id, goal_key),
        )
    ]
    return _node(
        node_id=f"goal:{goal_key}",
        parent_id=parent_id,
        level=level,
        node_type="business_goal",
        title=str(goal.get("title") or goal_key),
        status=str(goal.get("status") or "active"),
        goal_key=goal_key,
        stage_statuses=_aggregate_stages(lane_children),
        next_action=str(
            goal.get("success_metric") or "Open goal and decide next lane action."
        ),
        deep_link="/planning?tab=goals",
        detail_api=f"/api/planning/goals/{goal.get('id')}",
        updated_at=goal.get("updated_at"),
        children=lane_children,
    )


def _empty_workbench_snapshot(manifest: Any, manifest_id: int) -> dict[str, Any]:
    return {
        "root": None,
        "unassigned": {"count": 0, "items": []},
        "summary": {"active_goal_count": 0, "work_item_count": 0},
        "manifest": {
            "id": manifest_id,
            "updated_at": iso_timestamp(manifest.updated_at),
        },
    }


def _manifest_summary(manifest: Any, manifest_id: int) -> dict[str, Any]:
    return {
        "id": manifest_id,
        "version_name": str(manifest.version_name or ""),
        "cycle_label": str(manifest.cycle_label or ""),
        "updated_at": iso_timestamp(manifest.updated_at),
    }


def _primary_goal_lanes(
    db: Session, *, manifest_id: int, primary_goal_key: str
) -> list[dict[str, Any]]:
    parent_id = f"goal:{primary_goal_key}"
    return [
        _lane_node(
            lane_key="product_planner",
            parent_id=parent_id,
            level=1,
            goal_key=primary_goal_key,
            items=product_planner_items(db, manifest_id),
        ),
        _lane_node(
            lane_key="growth_lead",
            parent_id=parent_id,
            level=1,
            goal_key=primary_goal_key,
            items=growth_items(db),
        ),
        _lane_node(
            lane_key="software_engineer",
            parent_id=parent_id,
            level=1,
            goal_key=primary_goal_key,
            items=software_items(db, manifest_id, primary_goal_key),
        ),
    ]


def _secondary_goal_nodes(
    db: Session,
    *,
    manifest_id: int,
    active_goals: list[dict[str, Any]],
    primary_goal_key: str,
) -> list[dict[str, Any]]:
    return [
        _goal_node(
            goal=goal,
            parent_id=f"goal:{primary_goal_key}",
            level=1,
            manifest_id=manifest_id,
            db=db,
        )
        for goal in active_goals
        if str(goal.get("goal_key") or "") != primary_goal_key
    ]


def _root_goal_node(
    primary_goal: dict[str, Any], primary_goal_key: str, children: list[dict[str, Any]]
) -> dict[str, Any]:
    return _node(
        node_id=f"goal:{primary_goal_key}",
        parent_id=None,
        level=0,
        node_type="company_goal",
        title=str(primary_goal.get("title") or primary_goal_key),
        status=str(primary_goal.get("status") or "active"),
        goal_key=primary_goal_key,
        stage_statuses=_aggregate_stages(children),
        next_action=str(
            primary_goal.get("success_metric") or "Open active company goal."
        ),
        deep_link="/planning?tab=goals",
        detail_api=f"/api/planning/goals/{primary_goal.get('id')}",
        updated_at=primary_goal.get("updated_at"),
        children=children,
    )


@service_object_result
def mission_workbench_snapshot(db: Session) -> ServiceObjectResult:
    ensure_product_opportunity_table(db)
    manifest = ensure_active_manifest(db)
    manifest_id = int(manifest.id)
    active_goals = _active_goals(db, manifest_id)
    primary_goal = _primary_active_goal(active_goals)
    if not primary_goal:
        return _empty_workbench_snapshot(manifest, manifest_id)

    primary_goal_key = str(primary_goal.get("goal_key") or "")
    root_children = _primary_goal_lanes(
        db, manifest_id=manifest_id, primary_goal_key=primary_goal_key
    )
    root_children.extend(
        _secondary_goal_nodes(
            db,
            manifest_id=manifest_id,
            active_goals=active_goals,
            primary_goal_key=primary_goal_key,
        )
    )
    root = _root_goal_node(primary_goal, primary_goal_key, root_children)
    orphaned_items = unassigned_items(db, manifest_id)
    return {
        "root": root,
        "unassigned": {"count": len(orphaned_items), "items": orphaned_items},
        "summary": {
            "active_goal_count": len(active_goals),
            "work_item_count": _count_nodes(root) - 1,
        },
        "manifest": _manifest_summary(manifest, manifest_id),
    }


def _count_nodes(node: dict[str, Any]) -> int:
    return 1 + sum(_count_nodes(child) for child in node.get("children", []))
