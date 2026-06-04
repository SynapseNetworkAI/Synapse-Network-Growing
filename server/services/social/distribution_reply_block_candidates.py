"""Candidate helpers for content-task X reply blocks."""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server.database import (
    SocialReplyItemRow,
    SocialRepostCandidateRow,
    utcnow,
)
from server.database_social_distribution import SocialContentAssetRow
from server.services.social.distribution_reply_sources import ReplySourcePost


def candidate_for_reply_source(
    db: Session, source: ReplySourcePost, *, asset: SocialContentAssetRow
) -> SocialRepostCandidateRow:
    source_post_id = str(source.source_post_id or "").strip()
    candidate = _candidate_for_reply_source(
        db,
        source,
        source_already_has_reply=_source_already_has_reply(db, source_post_id),
    )
    _fill_candidate_from_source(candidate, source)
    if candidate.id is None:
        db.add(candidate)
    return candidate


def _source_already_has_reply(db: Session, source_post_id: str) -> bool:
    if not source_post_id:
        return False
    return bool(
        db.query(SocialReplyItemRow.id)
        .filter(
            SocialReplyItemRow.platform == "x",
            SocialReplyItemRow.source_post_id == source_post_id,
        )
        .first()
    )


def _candidate_for_reply_source(
    db: Session, source: ReplySourcePost, *, source_already_has_reply: bool
) -> SocialRepostCandidateRow:
    existing = _latest_matching_candidate(db, source)
    if existing is not None and not source_already_has_reply:
        return existing
    return SocialRepostCandidateRow(platform="x")


def _latest_matching_candidate(
    db: Session, source: ReplySourcePost
) -> SocialRepostCandidateRow | None:
    return (
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


def _fill_candidate_from_source(
    candidate: SocialRepostCandidateRow, source: ReplySourcePost
) -> None:
    candidate.source_url = source.source_url
    candidate.author_handle = source.author_handle
    candidate.source_text = source.source_text
    candidate.suggested_quote = (
        f"Add one concrete Synapse angle about {source.reply_angle.replace('_', ' ')}. "
        "Do not include links, URLs, domains, or source-post URLs; contribute a technical point only when it fits the source post."
    )
    candidate.relevance_score = 0.9
    candidate.status = "candidate"
    candidate.updated_at = utcnow()
