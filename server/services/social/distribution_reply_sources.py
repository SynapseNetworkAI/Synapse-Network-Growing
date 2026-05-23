"""Source-post adapters for X reply block generation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from server.database import SocialReplyItemRow, SocialTrendItemRow
from server.database_social_distribution import SocialContentAssetRow
from server.services.social.reply_records import extract_x_post_id


@dataclass(frozen=True)
class ReplySourcePost:
    source_url: str
    source_post_id: str
    author_handle: str | None
    source_text: str
    rationale: str
    opt_in_evidence: str | None = None


def _bounded(value: str, *, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}... [Truncated]"


def _line_source_posts(text: str) -> list[ReplySourcePost]:
    posts: list[ReplySourcePost] = []
    for line in str(text or "").splitlines():
        match = re.search(
            r"https?://(?:x|twitter)\.com/[A-Za-z0-9_]+/status(?:es)?/\d+", line
        )
        if not match:
            continue
        url = match.group(0)
        source_post_id = extract_x_post_id(url)
        if not source_post_id:
            continue
        handle_match = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]+)/status", url)
        context = (
            line.replace(url, "").strip(" -:\t") or f"Source X post {source_post_id}"
        )
        posts.append(
            ReplySourcePost(
                source_url=url.replace("twitter.com", "x.com"),
                source_post_id=source_post_id,
                author_handle=handle_match.group(1) if handle_match else None,
                source_text=_bounded(context, max_chars=1200),
                rationale="Provided in the content task source material.",
                opt_in_evidence=None,
            )
        )
    return posts


def _trend_source_posts(db: Session, *, limit: int) -> list[ReplySourcePost]:
    rows = (
        db.query(SocialTrendItemRow)
        .filter(
            SocialTrendItemRow.source_platform == "x",
            SocialTrendItemRow.source_url.isnot(None),
            SocialTrendItemRow.status.in_(("new", "saved", "candidate", "retained")),
        )
        .order_by(
            SocialTrendItemRow.relevance_score.desc(),
            SocialTrendItemRow.collected_at.desc(),
            SocialTrendItemRow.id.desc(),
        )
        .limit(max(1, limit * 3))
        .all()
    )
    posts: list[ReplySourcePost] = []
    for row in rows:
        source_post_id = extract_x_post_id(row.source_url)
        if not source_post_id:
            continue
        posts.append(
            ReplySourcePost(
                source_url=str(row.source_url),
                source_post_id=source_post_id,
                author_handle=row.author_handle,
                source_text=_bounded(f"{row.topic}: {row.summary}", max_chars=1200),
                rationale="Selected from stored X trend radar items.",
                opt_in_evidence=None,
            )
        )
    return posts[:limit]


def _dedupe_source_posts(
    posts: list[ReplySourcePost], *, limit: int
) -> list[ReplySourcePost]:
    seen: set[str] = set()
    deduped: list[ReplySourcePost] = []
    for post in posts:
        key = post.source_post_id or post.source_url
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(post)
        if len(deduped) >= limit:
            break
    return deduped


def _explicit_source_posts(
    source_posts: list[dict[str, object]] | None,
) -> list[ReplySourcePost]:
    posts: list[ReplySourcePost] = []
    for item in list(source_posts or []):
        if not isinstance(item, dict):
            continue
        posts.append(_explicit_source_post(item))
    return posts


def _explicit_source_post(item: dict[str, object]) -> ReplySourcePost:
    source_url = str(item.get("source_url") or "").strip()
    return ReplySourcePost(
        source_url=source_url,
        source_post_id=extract_x_post_id(source_url),
        author_handle=str(item.get("author_handle") or "").strip() or None,
        source_text=_bounded(
            str(item.get("source_text") or item.get("summary") or ""),
            max_chars=1200,
        ),
        rationale=_bounded(
            str(item.get("rationale") or "Provided by operator/browser collection."),
            max_chars=500,
        ),
        opt_in_evidence=_bounded(
            str(item.get("opt_in_evidence") or ""),
            max_chars=500,
        )
        or None,
    )


def _existing_reply_post_ids(db: Session) -> set[str]:
    return {
        str(row[0])
        for row in db.query(SocialReplyItemRow.source_post_id)
        .filter(SocialReplyItemRow.source_post_id.isnot(None))
        .all()
        if row[0]
    }


def usable_reply_source_posts(
    db: Session,
    asset: SocialContentAssetRow,
    *,
    source_posts: list[dict[str, object]] | None,
    target_count: int,
) -> list[ReplySourcePost]:
    explicit_posts = _explicit_source_posts(source_posts)
    parsed_posts = _line_source_posts(f"{asset.body or ''}\n{asset.summary or ''}")
    trend_posts = _trend_source_posts(db, limit=target_count)
    existing_post_ids = _existing_reply_post_ids(db)
    return [
        post
        for post in _dedupe_source_posts(
            explicit_posts + parsed_posts + trend_posts,
            limit=max(1, target_count),
        )
        if post.source_post_id
        and post.source_text
        and post.source_post_id not in existing_post_ids
    ]
