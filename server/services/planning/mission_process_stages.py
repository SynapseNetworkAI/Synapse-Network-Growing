"""Process-specific stage rails for Mission Workbench nodes."""

from __future__ import annotations

PROCESS_LABELS = {
    "engineering_delivery": (
        ("candidate", "Candidate"),
        ("requirement", "Requirement"),
        ("workflow", "Workflow"),
        ("pr", "PR"),
        ("release", "Release"),
        ("online", "Online"),
    ),
    "product_opportunity": (
        ("proposed", "Proposed"),
        ("review", "Review"),
        ("goal_requirement", "Goal/Requirement"),
        ("closed", "Deferred/Rejected"),
    ),
    "social_draft": (
        ("generated", "Generated"),
        ("needs_review", "Needs Review"),
        ("approved", "Approved/Edited"),
        ("published", "Published"),
        ("metrics", "Metrics"),
    ),
    "social_summary": (
        ("signals", "Signals"),
        ("drafts", "Drafts"),
        ("human_review", "Human Review"),
        ("published", "Published"),
        ("metrics", "Metrics"),
    ),
}


def _process_key_for_item_type(item_type: str) -> str:
    if item_type == "product_opportunity":
        return "product_opportunity"
    if item_type == "publishing_draft":
        return "social_draft"
    if item_type in {
        "social_daily_inventory",
        "social_review_queue",
        "social_metrics_loop",
    }:
        return "social_summary"
    if item_type in {
        "requirement_candidate",
        "requirement",
        "workflow",
        "release_task",
    }:
        return "engineering_delivery"
    return "mission_context"


def _process_stages(
    item_type: str, status: str, normalized_status: str
) -> list[dict[str, str]]:
    process_key = _process_key_for_item_type(item_type)
    labels = PROCESS_LABELS.get(process_key)
    if not labels:
        return []
    active_key = {
        "product_opportunity": _product_stage(status),
        "social_draft": _social_draft_stage(status),
        "social_summary": _social_summary_stage(item_type),
        "engineering_delivery": _engineering_stage(item_type),
    }.get(process_key, labels[0][0])
    active_index = _stage_index(labels, active_key)
    return [
        {
            "key": key,
            "label": label,
            "status": normalized_status
            if key == active_key
            else ("completed" if index < active_index else "missing"),
        }
        for index, (key, label) in enumerate(labels)
    ]


def _stage_index(labels: tuple[tuple[str, str], ...], key: str) -> int:
    return next((index for index, item in enumerate(labels) if item[0] == key), 0)


def _product_stage(status: str) -> str:
    if status in {"rejected", "deferred", "suppressed"}:
        return "closed"
    if status in {"approved", "materialized"}:
        return "goal_requirement"
    return "proposed"


def _social_draft_stage(status: str) -> str:
    if status == "published":
        return "published"
    if status == "approved":
        return "approved"
    if status in {"needs_review", "draft"}:
        return "needs_review"
    return "generated"


def _social_summary_stage(item_type: str) -> str:
    if item_type == "social_metrics_loop":
        return "metrics"
    if item_type == "social_review_queue":
        return "human_review"
    if item_type == "social_daily_inventory":
        return "drafts"
    return "signals"


def _engineering_stage(item_type: str) -> str:
    return {
        "requirement_candidate": "candidate",
        "requirement": "requirement",
        "workflow": "workflow",
        "release_task": "release",
    }.get(item_type, "candidate")
