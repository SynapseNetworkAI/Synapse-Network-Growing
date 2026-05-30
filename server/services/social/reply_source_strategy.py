"""Policy helpers for selecting high-signal X reply sources."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


AGENT_ECONOMY_REPLY_SOURCE_STRATEGY = "agent_economy_monetization"

SELECTABLE_SOURCE_BUCKETS = {
    "direct_pain",
    "ecosystem_discussion",
    "builder_problem",
}

DIRECT_PAIN_TERMS = (
    "agent payment",
    "agent payments",
    "api pricing",
    "api spend",
    "budget cap",
    "budgeted",
    "cost cap",
    "credit card",
    "how do agents pay",
    "metering",
    "monetization",
    "monetize",
    "paid api",
    "pay per call",
    "runaway spend",
    "spend control",
)

ECOSYSTEM_TERMS = (
    "x402",
    "mcp payment",
    "mcp paid",
    "paid tools",
    "usdc",
    "micropayment",
    "settlement",
    "provider registry",
    "agent marketplace",
    "agent wallet",
    "wallet",
    "receipt",
    "receipts",
    "external api access",
    "governed external api",
)

BUILDER_PROBLEM_TERMS = (
    "building an agent",
    "agent startup",
    "agent product",
    "indie",
    "solo founder",
    "api marketplace",
    "provider onboarding",
    "local ci",
    "deploy runner",
    "devtools",
)

BRAND_UNSAFE_TERMS = (
    "airdrop",
    "ape",
    "buy signal",
    "degen",
    "election",
    "meme coin",
    "moon",
    "price prediction",
    "pump",
    "rug",
    "token price",
    "trading signal",
)

PROMO_ONLY_TERMS = (
    "black friday",
    "discount",
    "giveaway",
    "launching today",
    "limited offer",
    "sign up now",
)

AGENT_TERMS = ("agent", "agents", "agentic", "ai agent", "mcp", "tool call", "tools")


@dataclass(frozen=True)
class ReplySourceStrategyAssessment:
    strategy: str
    source_bucket: str
    problem_fit_score: float
    conversation_quality_score: float
    reply_window_score: float
    audience_fit_score: float
    brand_safety_score: float
    total_score: float
    reply_angle: str
    selected: bool
    do_not_reply_reason: str | None
    matched_keywords: tuple[str, ...]

    def strategy_metadata(self) -> dict[str, object]:
        return {
            "strategy": self.strategy,
            "source_bucket": self.source_bucket,
            "problem_fit_score": round(self.problem_fit_score, 3),
            "conversation_quality_score": round(self.conversation_quality_score, 3),
            "reply_window_score": round(self.reply_window_score, 3),
            "audience_fit_score": round(self.audience_fit_score, 3),
            "brand_safety_score": round(self.brand_safety_score, 3),
            "total_score": round(self.total_score, 3),
            "reply_angle": self.reply_angle,
            "selected": self.selected,
            "do_not_reply_reason": self.do_not_reply_reason,
            "matched_keywords": list(self.matched_keywords),
        }


def assess_agent_economy_reply_source(
    *,
    source_text: str,
    topic: str = "",
    author_handle: str | None = None,
    collected_at: datetime | None = None,
) -> ReplySourceStrategyAssessment:
    """Score a source post for Synapse's agent-economy reply blocks."""

    combined = _normalize(f"{topic}\n{source_text}\n{author_handle or ''}")
    matched = _matched_keywords(combined)
    unsafe = _first_match(combined, BRAND_UNSAFE_TERMS)
    promo_only = _first_match(combined, PROMO_ONLY_TERMS)

    if unsafe:
        return _blocked("unsafe_or_speculative_context", matched)
    if promo_only and not _contains_any(combined, DIRECT_PAIN_TERMS + ECOSYSTEM_TERMS):
        return _blocked("generic_promotion_without_technical_context", matched)

    bucket = _source_bucket(combined)
    problem_fit = _problem_fit_score(combined)
    quality = _conversation_quality_score(source_text)
    window = _reply_window_score(collected_at)
    audience = _audience_fit_score(combined, author_handle)
    brand_safety = 1.0
    total = (
        (problem_fit * 0.42)
        + (quality * 0.22)
        + (window * 0.12)
        + (audience * 0.14)
        + (brand_safety * 0.10)
    )
    reply_angle = _reply_angle(combined)
    selected = bucket in SELECTABLE_SOURCE_BUCKETS and total >= 0.45
    reason = (
        None if selected else _do_not_reply_reason(bucket, problem_fit, quality, total)
    )
    return ReplySourceStrategyAssessment(
        strategy=AGENT_ECONOMY_REPLY_SOURCE_STRATEGY,
        source_bucket=bucket,
        problem_fit_score=problem_fit,
        conversation_quality_score=quality,
        reply_window_score=window,
        audience_fit_score=audience,
        brand_safety_score=brand_safety,
        total_score=total,
        reply_angle=reply_angle,
        selected=selected,
        do_not_reply_reason=reason,
        matched_keywords=matched,
    )


def _blocked(reason: str, matched: tuple[str, ...]) -> ReplySourceStrategyAssessment:
    return ReplySourceStrategyAssessment(
        strategy=AGENT_ECONOMY_REPLY_SOURCE_STRATEGY,
        source_bucket="blocked",
        problem_fit_score=0.0,
        conversation_quality_score=0.0,
        reply_window_score=0.0,
        audience_fit_score=0.0,
        brand_safety_score=0.0,
        total_score=0.0,
        reply_angle="do_not_reply",
        selected=False,
        do_not_reply_reason=reason,
        matched_keywords=matched,
    )


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _first_match(text: str, terms: tuple[str, ...]) -> str | None:
    return next((term for term in terms if term in text), None)


def _matched_keywords(text: str) -> tuple[str, ...]:
    terms = DIRECT_PAIN_TERMS + ECOSYSTEM_TERMS + BUILDER_PROBLEM_TERMS
    return tuple(term for term in terms if term in text)[:12]


def _source_bucket(text: str) -> str:
    if _contains_any(text, DIRECT_PAIN_TERMS):
        return "direct_pain"
    if _contains_any(text, ECOSYSTEM_TERMS):
        return "ecosystem_discussion"
    if _contains_any(text, BUILDER_PROBLEM_TERMS):
        return "builder_problem"
    if _contains_any(text, AGENT_TERMS):
        return "generic_agent_news"
    return "off_topic"


def _problem_fit_score(text: str) -> float:
    score = 0.0
    if _contains_any(text, AGENT_TERMS):
        score += 0.25
    score += min(0.45, 0.09 * sum(1 for term in DIRECT_PAIN_TERMS if term in text))
    score += min(0.25, 0.05 * sum(1 for term in ECOSYSTEM_TERMS if term in text))
    score += min(0.15, 0.05 * sum(1 for term in BUILDER_PROBLEM_TERMS if term in text))
    return min(1.0, score)


def _conversation_quality_score(source_text: str) -> float:
    text = str(source_text or "").strip()
    lowered = _normalize(text)
    if len(text) < 80:
        if _contains_any(lowered, DIRECT_PAIN_TERMS + ECOSYSTEM_TERMS):
            return 0.45
        return 0.20
    score = 0.45
    if "?" in text:
        score += 0.15
    if any(
        marker in lowered
        for marker in (
            "because",
            "how",
            "why",
            "tradeoff",
            "problem",
            "issue",
            "cost",
            "pricing",
        )
    ):
        score += 0.20
    if len(text) >= 180:
        score += 0.10
    return min(1.0, score)


def _reply_window_score(collected_at: datetime | None) -> float:
    if collected_at is None:
        return 0.65
    value = collected_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    age_hours = max(
        0.0,
        (datetime.now(timezone.utc) - value.astimezone(timezone.utc)).total_seconds()
        / 3600,
    )
    if 2 <= age_hours <= 24:
        return 1.0
    if age_hours < 2:
        return 0.85
    if age_hours <= 72:
        return 0.70
    return 0.35


def _audience_fit_score(text: str, author_handle: str | None) -> float:
    handle = _normalize(author_handle or "")
    score = 0.35
    if _contains_any(
        text,
        ("developer", "devtools", "builder", "provider", "api", "mcp", "open source"),
    ):
        score += 0.30
    if any(
        term in handle
        for term in ("dev", "ai", "agent", "mcp", "api", "builder", "founder")
    ):
        score += 0.20
    if _contains_any(
        text, ("indie", "solo founder", "startup", "infrastructure", "infra")
    ):
        score += 0.15
    return min(1.0, score)


def _reply_angle(text: str) -> str:
    if _contains_any(
        text,
        ("runaway spend", "spend control", "budget cap", "credit card", "api spend"),
    ):
        return "budget_cap"
    if _contains_any(text, ("pay per call", "paid api", "api pricing", "metering")):
        return "per_call_settlement"
    if _contains_any(text, ("provider registry", "agent marketplace", "marketplace")):
        return "provider_registry_proof"
    if _contains_any(text, ("receipt", "receipts", "evidence", "audit")):
        return "receipt_evidence"
    if _contains_any(text, ("human gate", "approval", "governance", "policy")):
        return "human_gate"
    if _contains_any(text, ("x402", "usdc", "settlement", "micropayment", "wallet")):
        return "api_metering"
    return "agent_economy_context"


def _do_not_reply_reason(
    bucket: str, problem_fit: float, quality: float, total: float
) -> str:
    if bucket in {"off_topic", "generic_agent_news"}:
        return f"{bucket}_not_specific_to_agent_economy"
    if quality < 0.45:
        return "source_lacks_technical_context"
    if problem_fit < 0.45:
        return "low_problem_fit"
    return f"score_below_threshold:{total:.2f}"


def update_strategy_metadata(
    metadata: dict[str, Any], assessment: ReplySourceStrategyAssessment
) -> dict[str, Any]:
    next_metadata = dict(metadata)
    next_metadata["reply_source_strategy"] = assessment.strategy_metadata()
    return next_metadata
