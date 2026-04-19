from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx
from sqlalchemy.orm import Session

from server import config
from server.database import ProjectRow, RequirementCandidateRow, utcnow
from server.services.planning.lifecycle import ensure_active_manifest


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _normalize_text(value: Any, *, max_len: int = 12000) -> str:
    text = str(value or "").strip()
    if len(text) > max_len:
        return text[:max_len].rstrip()
    return text


def _fingerprint(task: dict[str, Any]) -> str:
    topic = dict(task.get("topic") or {})
    stable = {
        "topic_id": str(task.get("topicId") or ""),
        "title": str(topic.get("title") or ""),
        "category": str(topic.get("category") or ""),
    }
    digest = hashlib.sha256(_json_dumps(stable).encode("utf-8")).hexdigest()[:24]
    return f"forum_feedback:{digest}"


def classify_forum_topic(task: dict[str, Any]) -> dict[str, Any]:
    topic = dict(task.get("topic") or {})
    title = _normalize_text(topic.get("title"), max_len=300).lower()
    body = _normalize_text(topic.get("body"), max_len=4000).lower()
    category = _normalize_text(topic.get("category"), max_len=80)
    text = f"{title}\n{body}"
    high_risk_terms = ("refund", "withdraw", "deposit", "usdc", "wallet", "auth", "password", "private key", "secret", "production")
    bug_terms = ("bug", "error", "failed", "failure", "timeout", "exception", "500", "crash", "broken", "cannot", "can't")

    if category == "Bugs" or any(term in text for term in bug_terms):
        classification = "bug"
    elif category == "Feature Requests":
        classification = "feature_request"
    elif category == "SDKs" or "docs" in text or "documentation" in text:
        classification = "docs_issue"
    elif "how" in text or "?" in text:
        classification = "question"
    else:
        classification = "needs_more_info"

    high_risk = any(term in text for term in high_risk_terms)
    priority = "high" if high_risk or classification == "bug" else "normal"
    if classification == "spam":
        priority = "low"
    return {
        "classification": classification,
        "priority": priority,
        "risk_level": "high" if high_risk else ("medium" if classification == "bug" else "low"),
        "high_risk": high_risk,
    }


def draft_forum_reply(task: dict[str, Any], classification: str, *, high_risk: bool) -> str:
    topic = dict(task.get("topic") or {})
    title = _normalize_text(topic.get("title"), max_len=160)
    if high_risk:
        return (
            f"Thanks for reporting this. We received your post about \"{title}\" and are moving it into an internal review path. "
            "For safety, please do not share private keys, secrets, or additional wallet-sensitive details publicly. "
            "Our ops team will review the evidence and follow up with the next safe step."
        )
    if classification == "bug":
        return (
            f"Thanks for the clear report. We have captured this as a potential bug and will triage it against the current gateway/support workflow. "
            "If you can add exact reproduction steps, timestamps, and any non-sensitive request IDs, that will help us verify it faster."
        )
    if classification == "feature_request":
        return (
            "Thanks for the suggestion. We have logged it for product review and will compare it with the current roadmap and active operating goals."
        )
    if classification == "docs_issue":
        return (
            "Thanks for calling this out. We will review the docs or SDK guidance and reply with the corrected integration path or a documentation update."
        )
    if classification == "needs_more_info":
        return (
            "Thanks for posting. Could you share a little more context, such as what you expected, what happened instead, and any non-sensitive IDs or screenshots?"
        )
    return "Thanks for the question. We are reviewing it and will reply with the most useful next step shortly."


def _fetch_pending_tasks() -> list[dict[str, Any]]:
    if not config.FORUM_FEEDBACK_GATEWAY_ADMIN_BASE_URL or not config.FORUM_FEEDBACK_GATEWAY_ADMIN_TOKEN:
        return []
    url = f"{config.FORUM_FEEDBACK_GATEWAY_ADMIN_BASE_URL}/api/admin/v1/forum/response-tasks/-/pending"
    response = httpx.get(
        url,
        params={"page_size": config.FORUM_FEEDBACK_MAX_TASKS},
        headers={"X-Growing-Service-Token": config.FORUM_FEEDBACK_GATEWAY_ADMIN_TOKEN},
        timeout=10,
    )
    response.raise_for_status()
    envelope = response.json()
    return list(((envelope.get("data") or {}).get("items") or []))


def _push_suggestion(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not config.FORUM_FEEDBACK_GATEWAY_ADMIN_BASE_URL or not config.FORUM_FEEDBACK_GATEWAY_ADMIN_TOKEN:
        return {"skipped": True, "reason": "gateway_admin_not_configured"}
    url = f"{config.FORUM_FEEDBACK_GATEWAY_ADMIN_BASE_URL}/api/admin/v1/forum/response-tasks/{task_id}/suggestion"
    response = httpx.post(
        url,
        json=payload,
        headers={"X-Growing-Service-Token": config.FORUM_FEEDBACK_GATEWAY_ADMIN_TOKEN},
        timeout=10,
    )
    response.raise_for_status()
    return dict((response.json() or {}).get("data") or {})


def _find_project(db: Session) -> ProjectRow | None:
    return (
        db.query(ProjectRow)
        .filter(ProjectRow.project_key == config.FORUM_FEEDBACK_DEFAULT_PROJECT_KEY)
        .first()
    )


def _create_or_reuse_bug_candidate(db: Session, task: dict[str, Any], analysis: dict[str, Any]) -> tuple[RequirementCandidateRow | None, bool]:
    if analysis["classification"] != "bug":
        return None, False
    manifest = ensure_active_manifest(db)
    fingerprint = _fingerprint(task)
    existing = (
        db.query(RequirementCandidateRow)
        .filter(
            RequirementCandidateRow.manifest_id == int(manifest.id),
            RequirementCandidateRow.candidate_fingerprint == fingerprint,
            RequirementCandidateRow.status.in_(["pending", "approved", "materialized"]),
        )
        .first()
    )
    if existing is not None:
        return existing, False
    topic = dict(task.get("topic") or {})
    project = _find_project(db)
    title = _normalize_text(topic.get("title"), max_len=160) or f"Forum bug report {task.get('topicId')}"
    body = _normalize_text(topic.get("body"), max_len=4000)
    row = RequirementCandidateRow(
        manifest_id=int(manifest.id),
        goal_key=config.FORUM_FEEDBACK_DEFAULT_GOAL_KEY,
        candidate_fingerprint=fingerprint,
        title=f"Forum bug: {title}",
        description_markdown=(
            "## Source\n"
            f"- forum topic: `{task.get('topicId')}`\n"
            f"- response task: `{task.get('responseTaskId')}`\n\n"
            "## User Report\n"
            f"{body}\n\n"
            "## Triage\n"
            "Agent classified this forum post as a potential bug. Operator approval is required before materialization."
        ),
        project_id=int(project.id) if project else None,
        project_key=str(project.project_key) if project else config.FORUM_FEEDBACK_DEFAULT_PROJECT_KEY,
        workflow_key="gateway_reliability_repair",
        priority="high" if analysis.get("high_risk") else "normal",
        risk_level=str(analysis.get("risk_level") or "medium"),
        confidence=0.72,
        rationale="Forum feedback sweep classified this post as an actionable bug signal.",
        expected_evidence_json=_json_dumps(["forum reply suggestion", "operator-approved candidate", "workflow verification evidence"]),
        metadata_json=_json_dumps({
            "source": "forum_feedback_sweep",
            "topic_id": task.get("topicId"),
            "response_task_id": task.get("responseTaskId"),
            "classification": analysis.get("classification"),
            "high_risk": bool(analysis.get("high_risk")),
        }),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(row)
    db.flush()
    return row, True


def run_forum_feedback_sweep(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
    tasks = _fetch_pending_tasks()
    processed: list[dict[str, Any]] = []
    created_candidate_ids: list[int] = []
    reused_candidate_ids: list[int] = []
    pushed_task_ids: list[str] = []
    for task in tasks:
        task_id = str(task.get("responseTaskId") or "")
        if not task_id:
            continue
        analysis = classify_forum_topic(task)
        candidate = None
        created_candidate = False
        if not dry_run:
            candidate, created_candidate = _create_or_reuse_bug_candidate(db, task, analysis)
        if candidate is not None:
            candidate_id = int(candidate.id)
            if created_candidate:
                created_candidate_ids.append(candidate_id)
            else:
                reused_candidate_ids.append(candidate_id)
        suggestion_payload = {
            "classification": analysis["classification"],
            "priority": analysis["priority"],
            "suggestedReply": draft_forum_reply(task, analysis["classification"], high_risk=bool(analysis["high_risk"])),
            "linkedRequirementCandidateId": str(int(candidate.id)) if candidate is not None else None,
            "metadata": {
                "triage": analysis,
                "growingGeneratedAt": utcnow().isoformat(),
            },
        }
        if not dry_run:
            _push_suggestion(task_id, suggestion_payload)
            pushed_task_ids.append(task_id)
        processed.append({
            "response_task_id": task_id,
            "topic_id": task.get("topicId"),
            "classification": analysis["classification"],
            "priority": analysis["priority"],
            "candidate_id": int(candidate.id) if candidate is not None else None,
            "pushed": not dry_run,
        })
    if not dry_run:
        db.commit()
    return {
        "dry_run": dry_run,
        "fetched": len(tasks),
        "processed": processed,
        "created_candidate_ids": created_candidate_ids,
        "reused_candidate_ids": reused_candidate_ids,
        "pushed_task_ids": pushed_task_ids,
    }
