"""Persistence helpers for X reply draft records."""

from __future__ import annotations

import json
import re
from typing import Any

from server.database import SocialReplyItemRow, SocialRepostCandidateRow
from server.services.social.reply_agent import GeneratedXReply


def _bounded_excerpt(value: str, *, max_chars: int = 1000) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}... [Truncated]"


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def extract_x_post_id(source_url: str | None) -> str:
    text = str(source_url or "").strip()
    if not text:
        return ""
    match = re.search(r"/status(?:es)?/(\d+)", text)
    if match:
        return match.group(1)
    match = re.search(r"(?:tweet_id|post_id|id)=(\d+)", text)
    return match.group(1) if match else ""


def reply_agent_failure_summary(exc: Exception) -> str:
    message = str(exc or "").strip()
    if message.startswith("agent_reply_generation_failed:"):
        return _bounded_excerpt(message, max_chars=900)
    return f"agent_reply_generation_failed: {_bounded_excerpt(message or exc.__class__.__name__, max_chars=860)}"


def _apply_candidate_context(
    row: SocialReplyItemRow, candidate: SocialRepostCandidateRow
) -> None:
    row.platform = "x"
    row.source_candidate_id = int(candidate.id)
    row.source_post_id = extract_x_post_id(candidate.source_url)
    row.source_author_handle = candidate.author_handle
    row.source_text = candidate.source_text
    row.author_handle = candidate.author_handle
    row.incoming_text = candidate.source_text
    row.intent = "repost_candidate_reply"
    row.source_url = str(candidate.source_url or "").strip()


def _base_metadata(
    candidate: SocialRepostCandidateRow, *, actor: str
) -> dict[str, Any]:
    return {
        "generated_by": "social_reply_agent_v1",
        "requested_by": actor,
        "source_candidate_id": int(candidate.id),
        "human_gate_required": True,
        "auto_publish": False,
        "template_fallback": False,
    }


def _apply_generation_failure(
    row: SocialReplyItemRow, metadata: dict[str, Any], failure_summary: str | None
) -> None:
    row.suggested_reply = ""
    row.generation_reason = (
        "Agent reply generation failed; no template fallback was used."
    )
    row.risk_level = "elevated"
    row.status = "failed"
    row.failure_summary = failure_summary or "agent_reply_generation_failed"
    metadata["generation_failed"] = True


def _blocked_summary(policy: dict[str, Any] | None) -> str:
    reasons = (policy or {}).get("blocked_reasons") or ["agent_risk_blocked"]
    return f"Blocked: {', '.join(reasons)}"


def _apply_generation_success(
    row: SocialReplyItemRow,
    metadata: dict[str, Any],
    *,
    generated: GeneratedXReply,
    policy: dict[str, Any] | None,
) -> None:
    blocked = (policy or {}).get(
        "status"
    ) == "blocked" or generated.risk_level == "blocked"
    row.suggested_reply = generated.suggested_reply
    row.generation_reason = generated.rationale
    row.risk_level = generated.risk_level
    row.status = "failed" if blocked else "needs_review"
    row.failure_summary = _blocked_summary(policy) if blocked else None
    metadata.update(generated.generation_metadata or {})
    metadata["policy_check"] = policy or {}


def apply_generated_reply_to_row(
    row: SocialReplyItemRow,
    candidate: SocialRepostCandidateRow,
    *,
    actor: str,
    generated: GeneratedXReply | None,
    failure_summary: str | None,
    policy: dict[str, Any] | None = None,
) -> None:
    _apply_candidate_context(row, candidate)
    metadata = _base_metadata(candidate, actor=actor)
    if generated is None:
        _apply_generation_failure(row, metadata, failure_summary)
    else:
        _apply_generation_success(row, metadata, generated=generated, policy=policy)
    row.metadata_json = _json_dumps(metadata)
