"""Daily X Article and X media content-task planner."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from server import schemas_social_distribution as dist_schema
from server.database import utcnow
from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionTaskRow,
)
from server.services.social.distribution import list_distribution_accounts
from server.services.social.distribution_article_packs import generate_x_article_pack
from server.services.social.distribution_board import _board_card
from server.services.social.distribution_content_tasks import create_content_task
from server.services.social.distribution_core import _record_event
from server.services.social.distribution_documents import (
    approved_canonical_article_document,
    expand_canonical_article,
    sync_task_document_from_task,
)
from server.services.social.distribution_generation import generate_distribution_tasks
from server.services.social.distribution_publish_lint import (
    BLOCKED,
    lint_distribution_task,
    lint_summary,
)
from server.services.social.distribution_task_types import X_ARTICLE_PACK, X_MEDIA_POST
from server.services.social.publishing import run_content_policy_check


DEFAULT_DAILY_X_STRATEGY = (
    "Promote Synapse Network as the settlement and payment layer for AI agents. "
    "Explain what the system does, how builders can let agents discover services, "
    "pay for API/data/model calls with capped budgets, inspect receipts, and how "
    "API or model providers can earn from metered agent usage."
)
TARGET_TASK_TYPES = (X_ARTICLE_PACK, X_MEDIA_POST)


def run_x_social_daily_content_task_planner(
    db: Session,
    *,
    strategy_key: str = "synapse_system_awareness",
    strategy_summary: str | None = None,
    local_date: str | None = None,
    actor: str = "x_daily_content_task_planner",
) -> dist_schema.SocialDailyXContentPlannerRunOut:
    """Create and advance the daily X Article and X media content tasks."""

    run_date = str(local_date or _operator_local_date()).strip()
    strategy = str(strategy_summary or DEFAULT_DAILY_X_STRATEGY).strip()
    created_asset_ids: list[int] = []
    existing_asset_ids: list[int] = []
    task_results: list[dist_schema.SocialDailyXContentTaskOut] = []
    for task_type in TARGET_TASK_TYPES:
        created, reused_existing = _ensure_daily_content_task(
            db,
            task_type=task_type,
            local_date=run_date,
            strategy_key=strategy_key,
            strategy_summary=strategy,
            actor=actor,
        )
        if reused_existing:
            existing_asset_ids.append(int(created.id))
        else:
            created_asset_ids.append(int(created.id))
        task_results.append(
            _advance_daily_content_task(
                db,
                created,
                task_type=task_type,
                actor=actor,
                reused_existing=reused_existing,
            )
        )
    return dist_schema.SocialDailyXContentPlannerRunOut(
        local_date=run_date,
        strategy_key=strategy_key,
        target_task_types=list(TARGET_TASK_TYPES),
        created_asset_ids=created_asset_ids,
        existing_asset_ids=existing_asset_ids,
        tasks=task_results,
        already_satisfied=not created_asset_ids
        and all(task.blocker is None for task in task_results),
    )


def _ensure_daily_content_task(
    db: Session,
    *,
    task_type: str,
    local_date: str,
    strategy_key: str,
    strategy_summary: str,
    actor: str,
) -> tuple[SocialContentAssetRow, bool]:
    title = _daily_title(task_type, local_date)
    detail = create_content_task(
        db,
        dist_schema.SocialContentTaskCreateRequest(
            title=title,
            task_type=task_type,
            source_material=_source_material(task_type, local_date, strategy_summary),
            target_audience=(
                "AI agent builders, API/data/model providers, developer operators, "
                "and technical founders evaluating agent payment infrastructure."
            ),
            target_platforms=["x"],
            goal_key="growth_social_conversion_loop",
            campaign_key=f"x_daily:{strategy_key}:{local_date}",
            post_intent="system_awareness",
            created_by=actor,
        ),
    )
    asset = db.get(SocialContentAssetRow, int(detail.id))
    if asset is None:
        raise RuntimeError("daily content task creation did not return an asset")
    metadata = _asset_metadata(asset)
    _tag_daily_metadata(
        asset,
        metadata={
            **metadata,
            "daily_strategy_key": strategy_key,
            "daily_local_date": local_date,
            "daily_content_task_planner": True,
            "agent_review_required": True,
            "human_gate_required": True,
            "auto_publish": False,
        },
    )
    db.commit()
    db.refresh(asset)
    return asset, bool(detail.agent_metadata.get("reused_existing"))


def _advance_daily_content_task(
    db: Session,
    asset: SocialContentAssetRow,
    *,
    task_type: str,
    actor: str,
    reused_existing: bool,
) -> dist_schema.SocialDailyXContentTaskOut:
    try:
        if _asset_ready_to_publish(asset):
            return _task_result(asset, task_type, "ready_to_publish", reused_existing)
        _ensure_canonical_article(db, asset, actor=actor)
        blocker = _agent_review_canonical_article(db, asset, actor=actor)
        if blocker:
            return _task_result(
                asset,
                task_type,
                "needs_human_review",
                reused_existing,
                blocker=blocker,
            )
        generated_task_ids = _generate_x_task_outputs(
            db, asset, task_type=task_type, actor=actor
        )
        task_blockers = _agent_review_generated_tasks(db, asset, actor=actor)
        if task_blockers:
            return _task_result(
                asset,
                task_type,
                "needs_human_review",
                reused_existing,
                generated_task_ids=generated_task_ids,
                blocker="; ".join(task_blockers[:3]),
            )
        return _task_result(
            asset,
            task_type,
            "ready_to_publish",
            reused_existing,
            generated_task_ids=generated_task_ids,
        )
    except Exception as exc:  # pragma: no cover - covered through API failure surface.
        db.rollback()
        return _task_result(
            asset,
            task_type,
            "blocked",
            reused_existing,
            blocker=f"daily_x_content_task_planner_failed: {str(exc)[:240]}",
        )


def _ensure_canonical_article(
    db: Session, asset: SocialContentAssetRow, *, actor: str
) -> None:
    if approved_canonical_article_document(db, asset) is not None:
        return
    if any(
        doc.document_kind == "canonical_article" for doc in list(asset.documents or [])
    ):
        return
    expand_canonical_article(
        db,
        int(asset.id),
        dist_schema.SocialDistributionExpandCanonicalArticleRequest(actor=actor),
    )
    db.refresh(asset)


def _agent_review_canonical_article(
    db: Session, asset: SocialContentAssetRow, *, actor: str
) -> str | None:
    approved = approved_canonical_article_document(db, asset)
    if approved is not None:
        return None
    candidates = [
        doc
        for doc in list(asset.documents or [])
        if doc.document_kind == "canonical_article"
    ]
    if not candidates:
        return "canonical_article_missing"
    document = max(candidates, key=lambda doc: int(doc.id))
    policy = run_content_policy_check(
        f"{document.title or ''}\n{document.body_markdown or ''}"
    )
    if policy.get("status") == "blocked":
        document.status = "needs_review"
        asset.status = "needs_review"
        _record_event(
            db,
            asset,
            None,
            "daily_x_content_agent_review_needs_human",
            actor,
            "Agent review blocked canonical article; human review required.",
            {"policy": policy, "document_id": int(document.id)},
        )
        db.commit()
        return "agent_review_policy_blocked"
    document.status = "approved"
    document.updated_at = utcnow()
    asset.status = "approved"
    asset.updated_at = utcnow()
    _record_event(
        db,
        asset,
        None,
        "daily_x_content_agent_review_approved",
        actor,
        "Agent review approved canonical article for X platform task generation.",
        {"document_id": int(document.id), "policy": policy},
    )
    db.commit()
    db.refresh(asset)
    return None


def _generate_x_task_outputs(
    db: Session,
    asset: SocialContentAssetRow,
    *,
    task_type: str,
    actor: str,
) -> list[int]:
    if task_type == X_ARTICLE_PACK:
        list_distribution_accounts(db)
        result = generate_x_article_pack(
            db,
            int(asset.id),
            dist_schema.SocialDistributionGenerateXArticlePackRequest(actor=actor),
        )
        return [result.article_task_id, result.teaser_task_id]
    accounts = [row for row in list_distribution_accounts(db) if row.platform == "x"]
    account_ids = [int(accounts[0].id)] if accounts else []
    generated = generate_distribution_tasks(
        db,
        int(asset.id),
        dist_schema.SocialDistributionGenerateTasksRequest(
            account_ids=account_ids,
            action="post",
            actor=actor,
        ),
    )
    return generated.generated_task_ids


def _agent_review_generated_tasks(
    db: Session, asset: SocialContentAssetRow, *, actor: str
) -> list[str]:
    blockers: list[str] = []
    tasks = (
        db.query(SocialDistributionTaskRow)
        .filter(SocialDistributionTaskRow.asset_id == int(asset.id))
        .all()
    )
    for task in tasks:
        if task.status not in {"needs_review", "draft_ready"}:
            continue
        blocker = _task_agent_review_blocker(task)
        metadata = _task_metadata(task)
        metadata["agent_review"] = {
            "actor": actor,
            "status": "needs_human_review" if blocker else "approved",
            "blocker": blocker,
            "auto_publish": False,
            "human_gate_required": True,
        }
        task.metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        if blocker:
            blockers.append(blocker)
            task.status = "needs_review"
            task.operator_checklist = _append_checklist(
                task.operator_checklist,
                f"Agent review requires human attention: {blocker}",
            )
        else:
            task.status = "approved"
        task.updated_at = utcnow()
        sync_task_document_from_task(
            db,
            task=task,
            metadata={"agent_review": metadata["agent_review"]},
        )
        _record_event(
            db,
            asset,
            task,
            "daily_x_content_task_agent_reviewed",
            actor,
            "Agent reviewed generated X task; public publish still requires Human Gate.",
            {"status": task.status, "blocker": blocker},
        )
    asset.status = "ready"
    asset.updated_at = utcnow()
    db.commit()
    db.refresh(asset)
    return blockers


def _task_agent_review_blocker(task: SocialDistributionTaskRow) -> str | None:
    metadata = _task_metadata(task)
    lint = lint_distribution_task(
        platform=task.platform,
        channel_key=task.channel_key,
        title=task.platform_title,
        body=task.platform_body,
        metadata=metadata,
    )
    if lint.status == BLOCKED:
        return f"platform_publish_lint_blocked: {lint_summary(lint)}"
    policy = run_content_policy_check(task.platform_body or "")
    if policy.get("status") == "blocked":
        reasons = ", ".join(str(item) for item in policy.get("blocked_reasons", []))
        return f"policy_blocked: {reasons or 'content_policy'}"
    return None


def _asset_ready_to_publish(asset: SocialContentAssetRow) -> bool:
    card = _board_card(asset)
    return card.column_key == "ready_to_publish" and card.ready_to_publish_count > 0


def _task_result(
    asset: SocialContentAssetRow,
    task_type: str,
    stage: str,
    reused_existing: bool,
    *,
    generated_task_ids: list[int] | None = None,
    blocker: str | None = None,
) -> dist_schema.SocialDailyXContentTaskOut:
    card = _board_card(asset)
    return dist_schema.SocialDailyXContentTaskOut(
        task_type=task_type,
        asset_id=int(asset.id),
        title=asset.title,
        stage=stage,
        column_key=card.column_key,
        ready_to_publish_count=card.ready_to_publish_count,
        reused_existing=reused_existing,
        generated_task_ids=generated_task_ids or [],
        blocker=blocker,
    )


def _daily_title(task_type: str, local_date: str) -> str:
    label = "X Article" if task_type == X_ARTICLE_PACK else "X Media"
    return f"{label} Daily Synapse System Awareness - {local_date}"


def _source_material(task_type: str, local_date: str, strategy_summary: str) -> str:
    format_note = (
        "Create a long-form X Article pack with a cover image and teaser."
        if task_type == X_ARTICLE_PACK
        else "Create an X media post with one useful image/visual angle and concise copy."
    )
    return "\n".join(
        [
            f"Daily strategy date: {local_date}",
            strategy_summary,
            format_note,
            "Must explain: what Synapse Network is, what functions it provides, how providers can earn, and how agents can pay for APIs, data, and large-model services with receipts and budget controls.",
            "Do not claim an external post was published. Stop at human-gated publish readiness.",
        ]
    )


def _operator_local_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _asset_metadata(asset: SocialContentAssetRow) -> dict[str, object]:
    try:
        payload = json.loads(asset.agent_metadata_json or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _tag_daily_metadata(
    asset: SocialContentAssetRow, *, metadata: dict[str, object]
) -> None:
    asset.agent_metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    asset.updated_at = utcnow()


def _task_metadata(task: SocialDistributionTaskRow) -> dict[str, object]:
    try:
        payload = json.loads(task.metadata_json or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _append_checklist(existing: str | None, addition: str) -> str:
    base = str(existing or "").strip()
    return f"{base}\n{addition}".strip() if base else addition
