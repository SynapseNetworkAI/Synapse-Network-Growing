"""Bridge content-task reply blocks into the X reply candidate queue."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server import config
from server.database import (
    SocialReplyItemRow,
    SocialRepostCandidateRow,
    utcnow,
)
from server.database_social_distribution import SocialContentAssetRow
from server.services.result_objects import ServiceObjectResult, service_object_result
from server.services.social.distribution import get_content_asset
from server.services.social.distribution_core import _record_event
from server.services.social.publishing import (
    _create_reply_from_repost_candidate,
    publish_social_reply_to_x,
    run_content_policy_check,
)
from server.schemas import SocialReplyPublishRequest
from server.services.social.distribution_reply_sources import (
    ReplySourcePost,
    usable_reply_source_posts,
)


@dataclass
class ReplyBlockGeneration:
    reply_ids: list[int]
    failed_reply_ids: list[int]
    source_candidate_ids: list[int]
    processed_source_count: int
    published_reply_ids: list[int] | None = None
    timed_out: bool = False
    blocked_reason: str | None = None
    publish_mode: str = "agent_approved_needs_manual_publish"
    approval_ref_configured: bool = False
    auto_publish: bool = False


DEFAULT_REPLY_BLOCK_MAX_SECONDS = 90
DEFAULT_REPLY_BLOCK_PER_REPLY_TIMEOUT_SECONDS = 30


def _monotonic_seconds() -> float:
    return time.monotonic()


def _json_loads(raw: str | None) -> dict[str, Any]:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _is_engagement_reply_asset(asset: SocialContentAssetRow) -> bool:
    metadata = _json_loads(asset.agent_metadata_json)
    targets = metadata.get("target_platforms")
    target_platforms = (
        {str(item).strip().lower() for item in targets if item}
        if isinstance(targets, list)
        else set()
    )
    return (
        str(metadata.get("post_intent") or "").strip() == "engagement_reply"
        or str(asset.asset_type or "").strip() in {"reply", "engagement_reply"}
        or (
            target_platforms == {"x"}
            and "reply" in f"{asset.title} {asset.body or ''}".lower()
        )
    )


def _candidate_for_source(
    db: Session, source: ReplySourcePost, *, asset: SocialContentAssetRow
) -> SocialRepostCandidateRow:
    existing = (
        db.query(SocialRepostCandidateRow)
        .filter(
            SocialRepostCandidateRow.platform == "x",
            or_(
                SocialRepostCandidateRow.source_url == source.source_url,
                SocialRepostCandidateRow.source_text == source.source_text,
            ),
        )
        .order_by(SocialRepostCandidateRow.id.desc())
        .first()
    )
    candidate = existing or SocialRepostCandidateRow(platform="x")
    candidate.source_url = source.source_url
    candidate.author_handle = source.author_handle
    candidate.source_text = source.source_text
    candidate.suggested_quote = (
        "Add one concrete Synapse angle about governed agent actions, API access, budgets, "
        "provider monetization, or settlement only when it fits the source post."
    )
    candidate.relevance_score = 0.9
    candidate.status = "candidate"
    candidate.updated_at = utcnow()
    if existing is None:
        db.add(candidate)
    return candidate


def _agent_approve_reply(
    row: SocialReplyItemRow, *, actor: str, approved_status: str
) -> None:
    if row.status != "needs_review" or not row.suggested_reply:
        return
    policy = run_content_policy_check(row.suggested_reply)
    metadata = _json_loads(row.metadata_json)
    metadata["agent_quality_review"] = {
        "status": policy["status"],
        "reviewed_by": actor,
        "blocked_reasons": policy.get("blocked_reasons", []),
        "warnings": policy.get("warnings", []),
    }
    row.metadata_json = _json_dumps(metadata)
    if policy["status"] == "passed":
        row.status = approved_status
        row.reviewed_by = actor
    else:
        row.status = "failed"
        row.failure_summary = f"Blocked: {', '.join(policy.get('blocked_reasons') or ['agent_quality_review'])}"
    row.updated_at = utcnow()


def _generate_replies_for_sources(
    db: Session,
    asset: SocialContentAssetRow,
    sources: list[ReplySourcePost],
    *,
    actor: str,
    agent_review: bool,
    max_seconds: int,
    per_reply_timeout_seconds: int,
    publish_mode: str,
) -> ReplyBlockGeneration:
    started_at = _monotonic_seconds()
    reply_ids: list[int] = []
    candidate_ids: list[int] = []
    failed_reply_ids: list[int] = []
    for source in sources:
        elapsed = _monotonic_seconds() - started_at
        if elapsed >= max(1, int(max_seconds)):
            return ReplyBlockGeneration(
                reply_ids=reply_ids,
                failed_reply_ids=failed_reply_ids,
                source_candidate_ids=candidate_ids,
                processed_source_count=len(candidate_ids),
                timed_out=True,
                blocked_reason=(
                    f"x_reply_block_generation_timeout: exceeded {int(max_seconds)}s "
                    f"after {len(candidate_ids)} source posts"
                ),
            )
        candidate = _candidate_for_source(db, source, asset=asset)
        db.flush()
        reply = _create_reply_from_repost_candidate(
            db,
            candidate,
            actor=actor,
            force_regenerate=False,
            reply_timeout_seconds=per_reply_timeout_seconds,
        )
        metadata = _json_loads(reply.metadata_json)
        metadata["x_reply_compliance"] = {
            "approval_ref_configured": bool(config.X_AI_REPLY_APPROVAL_REF),
            "opt_in_evidence": source.opt_in_evidence,
            "publish_mode": publish_mode,
            "browser_automation_publish_allowed": False,
        }
        reply.metadata_json = _json_dumps(metadata)
        if agent_review:
            _agent_approve_reply(reply, actor=actor, approved_status=publish_mode)
        candidate_ids.append(int(candidate.id))
        if reply.status == "failed":
            failed_reply_ids.append(int(reply.id))
        else:
            reply_ids.append(int(reply.id))
    return ReplyBlockGeneration(
        reply_ids=reply_ids,
        failed_reply_ids=failed_reply_ids,
        source_candidate_ids=candidate_ids,
        processed_source_count=len(sources),
        publish_mode=publish_mode,
        approval_ref_configured=bool(config.X_AI_REPLY_APPROVAL_REF),
    )


def _auto_publish_allowed(
    sources: list[ReplySourcePost], *, requested: bool
) -> tuple[bool, str, str | None]:
    if not requested:
        return False, "agent_approved_needs_manual_publish", None
    if not config.X_AI_REPLY_APPROVAL_REF:
        return (
            False,
            "agent_approved_needs_manual_publish",
            "missing_x_ai_reply_approval_ref",
        )
    missing = [
        source.source_post_id or source.source_url
        for source in sources
        if not str(source.opt_in_evidence or "").strip()
    ]
    if missing:
        return (
            False,
            "agent_blocked_missing_opt_in_evidence",
            (
                "x_auto_reply_requires_source_post_opt_in_evidence: "
                + ", ".join(missing[:5])
            ),
        )
    return True, "approved", None


def _publish_approved_replies(
    db: Session, reply_ids: list[int], *, actor: str
) -> tuple[list[int], list[int]]:
    published_ids: list[int] = []
    failed_ids: list[int] = []
    for reply_id in reply_ids:
        published = publish_social_reply_to_x(
            db,
            reply_id,
            SocialReplyPublishRequest(actor=actor),
        )
        if published.status == "published":
            published_ids.append(int(reply_id))
        else:
            failed_ids.append(int(reply_id))
    return published_ids, failed_ids


def _require_reply_block_asset(db: Session, asset_id: int) -> SocialContentAssetRow:
    asset = db.get(SocialContentAssetRow, asset_id)
    if asset is None:
        raise ValueError("Content asset not found.")
    if not _is_engagement_reply_asset(asset):
        raise ValueError("content asset is not an X engagement reply task.")
    return asset


def _usable_reply_posts_or_raise(
    db: Session,
    asset: SocialContentAssetRow,
    *,
    source_posts: list[dict[str, object]] | None,
    target_count: int,
) -> list[ReplySourcePost]:
    usable_posts = usable_reply_source_posts(
        db,
        asset,
        source_posts=source_posts,
        target_count=target_count,
    )
    if usable_posts:
        return usable_posts
    raise ValueError(
        "reply block requires real X source posts with text; provide 5 source URLs or sync watchlist trends first."
    )


def _publish_generation_if_allowed(
    db: Session,
    generation: ReplyBlockGeneration,
    *,
    auto_publish_allowed: bool,
    compliance_blocker: str | None,
    actor: str,
) -> None:
    if auto_publish_allowed and generation.reply_ids and not generation.timed_out:
        published_ids, failed_ids = _publish_approved_replies(
            db,
            generation.reply_ids,
            actor=actor,
        )
        generation.published_reply_ids = published_ids
        generation.failed_reply_ids.extend(failed_ids)
        generation.auto_publish = True
    elif compliance_blocker and not generation.blocked_reason:
        generation.blocked_reason = compliance_blocker


def _write_reply_block_result(
    db: Session,
    asset: SocialContentAssetRow,
    result: ReplyBlockGeneration,
    *,
    target_count: int,
    actor: str,
    agent_review: bool,
    auto_publish: bool,
    publish_mode: str,
) -> None:
    metadata = _json_loads(asset.agent_metadata_json)
    metadata["reply_block"] = {
        "last_generated_at": utcnow().isoformat(),
        "target_count": int(target_count),
        "reply_ids": result.reply_ids,
        "failed_reply_ids": result.failed_reply_ids,
        "source_candidate_ids": result.source_candidate_ids,
        "agent_review": bool(agent_review),
        "auto_publish": bool(auto_publish),
        "publish_mode": publish_mode,
        "approval_ref_configured": bool(result.approval_ref_configured),
        "published_reply_ids": result.published_reply_ids or [],
        "timed_out": bool(result.timed_out),
        "blocked_reason": result.blocked_reason,
    }
    asset.agent_metadata_json = _json_dumps(metadata)
    asset.status = "failed" if result.timed_out or not result.reply_ids else "ready"
    asset.updated_at = utcnow()
    _record_event(
        db,
        asset,
        None,
        "x_reply_block_candidates_generated",
        actor,
        (
            f"Generated {len(result.reply_ids)} X reply candidates from "
            f"{result.processed_source_count} source posts."
        ),
        {
            "reply_ids": result.reply_ids,
            "failed_reply_ids": result.failed_reply_ids,
            "source_candidate_ids": result.source_candidate_ids,
            "auto_publish": bool(auto_publish),
            "publish_mode": publish_mode,
            "approval_ref_configured": bool(result.approval_ref_configured),
            "published_reply_ids": result.published_reply_ids or [],
            "timed_out": bool(result.timed_out),
            "blocked_reason": result.blocked_reason,
        },
    )
    if result.timed_out:
        _record_event(
            db,
            asset,
            None,
            "x_reply_block_generation_timeout",
            actor,
            result.blocked_reason or "X reply block generation timed out.",
            {
                "reply_ids": result.reply_ids,
                "failed_reply_ids": result.failed_reply_ids,
                "source_candidate_ids": result.source_candidate_ids,
                "processed_source_count": result.processed_source_count,
                "auto_publish": bool(auto_publish),
            },
        )


@service_object_result
def generate_x_reply_block_candidates(
    db: Session,
    *,
    asset_id: int,
    source_posts: list[dict[str, object]] | None = None,
    target_count: int = 5,
    actor: str = "agent",
    agent_review: bool = True,
    max_seconds: int = DEFAULT_REPLY_BLOCK_MAX_SECONDS,
    per_reply_timeout_seconds: int = DEFAULT_REPLY_BLOCK_PER_REPLY_TIMEOUT_SECONDS,
    auto_publish: bool = False,
) -> ServiceObjectResult:
    asset = _require_reply_block_asset(db, asset_id)
    usable_posts = _usable_reply_posts_or_raise(
        db,
        asset,
        source_posts=source_posts,
        target_count=target_count,
    )
    auto_publish_allowed, publish_mode, compliance_blocker = _auto_publish_allowed(
        usable_posts[: max(1, target_count)],
        requested=auto_publish,
    )
    if auto_publish and compliance_blocker and config.X_AI_REPLY_APPROVAL_REF:
        raise ValueError(compliance_blocker)

    generation = _generate_replies_for_sources(
        db,
        asset,
        usable_posts[: max(1, target_count)],
        actor=actor,
        agent_review=agent_review,
        max_seconds=max_seconds,
        per_reply_timeout_seconds=per_reply_timeout_seconds,
        publish_mode=publish_mode,
    )
    _publish_generation_if_allowed(
        db,
        generation,
        auto_publish_allowed=auto_publish_allowed,
        compliance_blocker=compliance_blocker,
        actor=actor,
    )
    _write_reply_block_result(
        db,
        asset,
        generation,
        target_count=target_count,
        actor=actor,
        agent_review=agent_review,
        auto_publish=auto_publish_allowed,
        publish_mode=publish_mode,
    )
    db.commit()
    return {
        "asset": get_content_asset(db, int(asset.id)),
        "reply_ids": generation.reply_ids,
        "failed_reply_ids": generation.failed_reply_ids,
        "source_candidate_ids": generation.source_candidate_ids,
        "processed_source_count": generation.processed_source_count,
        "auto_publish": bool(auto_publish_allowed),
        "agent_review": bool(agent_review),
        "timed_out": bool(generation.timed_out),
        "blocked_reason": generation.blocked_reason or compliance_blocker,
        "publish_mode": publish_mode,
        "approval_ref_configured": bool(config.X_AI_REPLY_APPROVAL_REF),
    }


@service_object_result
def run_x_social_daily_reply_block_publisher(db: Session) -> ServiceObjectResult:
    now = datetime.now(timezone.utc)
    rows = (
        db.query(SocialContentAssetRow)
        .filter(
            SocialContentAssetRow.status.in_(("draft", "active", "ready", "proposed"))
        )
        .order_by(
            SocialContentAssetRow.updated_at.asc(), SocialContentAssetRow.id.asc()
        )
        .limit(50)
        .all()
    )
    for asset in rows:
        metadata = _json_loads(asset.agent_metadata_json)
        if str(metadata.get("post_intent") or "") != "engagement_reply":
            continue
        planned_raw = str(metadata.get("planned_publish_at") or "").strip()
        if planned_raw:
            try:
                planned_at = datetime.fromisoformat(planned_raw.replace("Z", "+00:00"))
            except ValueError:
                planned_at = now
            if planned_at.astimezone(timezone.utc) > now:
                continue
        try:
            result = generate_x_reply_block_candidates(
                db,
                asset_id=int(asset.id),
                target_count=5,
                actor="x_social_daily_reply_block_publisher",
                agent_review=True,
                max_seconds=DEFAULT_REPLY_BLOCK_MAX_SECONDS,
                per_reply_timeout_seconds=DEFAULT_REPLY_BLOCK_PER_REPLY_TIMEOUT_SECONDS,
            )
        except ValueError as exc:
            return {
                "processed": False,
                "asset_id": int(asset.id),
                "blocked_reason": str(exc),
                "auto_publish": False,
            }
        return {
            "processed": True,
            "asset_id": int(asset.id),
            "result": dict(result),
            "auto_publish": False,
        }
    return {
        "processed": False,
        "asset_id": None,
        "blocked_reason": "no_due_engagement_reply_asset",
        "auto_publish": False,
    }
