"""Platform content contracts for social distribution drafts."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from server.services.social.distribution_core import _normalize_platform

X_WEIGHTED_CHAR_LIMIT = 280
X_LONG_POST_SOFT_LIMIT = 4000

_URL_RE = re.compile(r"https?://[^\s]+", flags=re.IGNORECASE)


def x_weighted_character_count(text: str) -> int:
    """Conservative X weighted count: URLs are 23, wide/CJK chars are 2."""
    value = str(text or "")
    total = 0
    cursor = 0
    for match in _URL_RE.finditer(value):
        total += _weighted_non_url_count(value[cursor : match.start()])
        total += 23
        cursor = match.end()
    total += _weighted_non_url_count(value[cursor:])
    return total


def platform_format_kind(platform: str) -> str:
    normalized = _normalize_platform(platform)
    if normalized == "x":
        return "x_long_post"
    if normalized == "hacker_news":
        return "hn_submission"
    if normalized in {"reddit", "v2ex"}:
        return "discussion_post"
    if normalized in {"dev", "devto", "hashnode"}:
        return "long_article"
    return "discussion_post"


def platform_target_length(platform: str) -> str:
    normalized = _normalize_platform(platform)
    if normalized == "x":
        return "X Premium long post, density-driven, max 4000 chars"
    if normalized == "hacker_news":
        return "title 40-80 chars plus optional first comment draft"
    if normalized == "reddit":
        return "title <= 300 chars; body 1200-3000 chars"
    if normalized == "v2ex":
        return "Chinese title 20-60 chars; body 800-2000 Chinese chars"
    if normalized in {"dev", "devto", "hashnode"}:
        return "long Markdown article, 1200-2500 words"
    return "platform-native post sized to community norms"


def text_length_metadata(platform: str, body: str) -> dict[str, object]:
    normalized = _normalize_platform(platform)
    if normalized == "x":
        return {
            "character_count": len(str(body or "")),
            "weighted_counts": [x_weighted_character_count(str(body or ""))],
            "counting_mode": "conservative",
        }
    if normalized in {"dev", "devto", "hashnode"}:
        return {"word_count": _word_count(body)}
    return {"character_count": len(str(body or ""))}


def normalize_x_payload(
    payload: dict[str, Any], *, fallback_title: str
) -> tuple[str, str, dict[str, object]]:
    x_format, tweets, post_text = _normalize_x_format_and_content(payload)
    if x_format == "long_post":
        body = _validated_x_long_post_text(post_text)
        title = _x_title(payload, fallback_title=fallback_title, x_format=x_format)
        metadata = _x_long_post_metadata(body)
        if payload.get("rationale"):
            metadata["rationale"] = str(payload.get("rationale"))
        return title, body, metadata

    weighted_counts = _validated_x_weighted_counts(tweets)
    body = tweets[0] if x_format == "single" else _thread_body(tweets)
    title = _x_title(payload, fallback_title=fallback_title, x_format=x_format)
    metadata = _x_metadata(x_format, tweets, body, weighted_counts)
    if payload.get("rationale"):
        metadata["rationale"] = str(payload.get("rationale"))
    return title, body, metadata


def x_tweets_from_metadata(
    metadata: dict[str, Any], fallback_body: str | None
) -> list[str]:
    if str(metadata.get("x_format") or "").strip().lower() == "long_post":
        return []
    tweets = metadata.get("tweets")
    if isinstance(tweets, list):
        cleaned = [str(item).strip() for item in tweets if str(item).strip()]
        if cleaned:
            return cleaned
    body = str(fallback_body or "").strip()
    return [body] if body else []


def x_format_from_metadata(metadata: dict[str, Any], tweets: list[str]) -> str:
    x_format = str(metadata.get("x_format") or "").strip().lower()
    format_kind = str(metadata.get("format_kind") or "").strip().lower()
    if x_format in {"article_pack", "x_article_pack"}:
        return "article_pack"
    if format_kind == "x_article_pack":
        return "article_pack"
    if x_format in {"long_post", "x_long_post", "premium_long_post"}:
        return "long_post"
    if format_kind in {"long_post", "x_long_post", "premium_long_post"}:
        return "long_post"
    if x_format in {"single", "thread"}:
        return x_format
    return "single" if len(tweets) <= 1 else "thread"


def x_long_post_text_from_metadata(
    metadata: dict[str, Any], fallback_body: str | None
) -> str:
    for key in ("long_post_text", "post_text"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return str(fallback_body or "").strip()


def x_teaser_media_manifest(metadata: dict[str, Any]) -> dict[str, Any]:
    media = metadata.get("x_teaser_media")
    return media if isinstance(media, dict) else {}


def _normalize_x_format_and_content(
    payload: dict[str, Any],
) -> tuple[str, list[str], str]:
    x_format = str(payload.get("x_format") or "").strip().lower()
    tweets = [
        str(item).strip() for item in payload.get("tweets", []) if str(item).strip()
    ]
    post_text = str(payload.get("post_text") or "").strip()
    if x_format == "long_post" and not post_text:
        post_text = str(payload.get("platform_body") or "").strip()
    if not x_format and post_text:
        x_format = "long_post"
    if not x_format and tweets:
        x_format = "single" if len(tweets) == 1 else "thread"
    _validate_x_shape(x_format, tweets, post_text)
    return x_format, tweets, post_text


def _validate_x_shape(x_format: str, tweets: list[str], post_text: str) -> None:
    if x_format not in {"single", "thread", "long_post"}:
        raise ValueError(
            "x_draft_invalid: x_format must be single, thread, or long_post."
        )
    if x_format == "long_post":
        if not post_text:
            raise ValueError("x_draft_invalid: post_text must not be empty.")
        return
    if not tweets:
        raise ValueError("x_draft_invalid: tweets must not be empty.")
    if x_format == "single" and len(tweets) != 1:
        raise ValueError("x_draft_invalid: single format requires exactly one tweet.")
    if x_format == "thread" and len(tweets) < 2:
        raise ValueError("x_draft_invalid: thread format requires at least two tweets.")


def _validated_x_weighted_counts(tweets: list[str]) -> list[int]:
    weighted_counts = [x_weighted_character_count(tweet) for tweet in tweets]
    over_limit = [
        index + 1
        for index, count in enumerate(weighted_counts)
        if count > X_WEIGHTED_CHAR_LIMIT
    ]
    if over_limit:
        raise ValueError(
            "x_draft_invalid: tweet weighted count exceeds 280 at "
            + ", ".join(str(index) for index in over_limit)
        )
    return weighted_counts


def _x_title(payload: dict[str, Any], *, fallback_title: str, x_format: str) -> str:
    return str(payload.get("platform_title") or "").strip() or (
        fallback_title
        if x_format in {"single", "long_post"}
        else f"X thread: {fallback_title}"
    )


def _x_metadata(
    x_format: str, tweets: list[str], body: str, weighted_counts: list[int]
) -> dict[str, object]:
    return {
        "format_kind": "single_x_post" if x_format == "single" else "x_thread",
        "target_length": platform_target_length("x"),
        "character_count": len(body),
        "weighted_counts": weighted_counts,
        "x_format": x_format,
        "tweets": tweets,
        "counting_mode": "conservative",
    }


def _validated_x_long_post_text(post_text: str) -> str:
    body = str(post_text or "").strip()
    if not body:
        raise ValueError("x_draft_invalid: post_text must not be empty.")
    if len(body) > X_LONG_POST_SOFT_LIMIT:
        raise ValueError(
            f"x_draft_invalid: long post exceeds {X_LONG_POST_SOFT_LIMIT} chars."
        )
    return body


def _x_long_post_metadata(body: str) -> dict[str, object]:
    return {
        "format_kind": "x_long_post",
        "target_length": platform_target_length("x"),
        "character_count": len(body),
        "soft_max_chars": X_LONG_POST_SOFT_LIMIT,
        "x_format": "long_post",
        "long_post_text": body,
        "premium_required": True,
        "counting_mode": "plain_character_count",
    }


def _weighted_non_url_count(text: str) -> int:
    total = 0
    for char in text:
        if unicodedata.category(char) in {"Mn", "Me"}:
            continue
        total += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
    return total


def _word_count(text: str) -> int:
    words = re.findall(r"\b[\w'-]+\b", str(text or ""), flags=re.UNICODE)
    return len(words)


def _thread_body(tweets: list[str]) -> str:
    total = len(tweets)
    return "\n\n".join(
        f"{index + 1}/{total}\n{tweet}" for index, tweet in enumerate(tweets)
    )
