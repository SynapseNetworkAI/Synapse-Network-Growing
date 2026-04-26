"""Social publishing service with human-gated X posting."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from server import config
from server.database import SocialAccountRow, SocialPostDraftRow, SocialPublishEventRow, utcnow
from server.schemas import (
    SocialPostCreateRequest,
    SocialPostDraftOut,
    SocialPostGenerateDraftRequest,
    SocialPostPatchRequest,
    SocialPostPublishRequest,
    SocialPostRewriteRequest,
)
from server.services.agents.llm_adapter import get_provider

DEFAULT_X_HANDLE = "SynapseNetworkA"
DEFAULT_X_SECRET_REF = "x-official-oauth2-user-token"
X_POST_URL = "https://api.x.com/2/tweets"
ALLOWED_STATUSES = {"draft", "needs_review", "approved", "publishing", "published", "failed", "rejected"}
HUMAN_SETTLED_STATUSES = {"published", "rejected"}
SOCIAL_CONTEXT_MAX_CHARS = 1100
SOCIAL_SKILL_MAX_CHARS = 900
SOCIAL_LAUNCH_SKILL_MAX_CHARS = 600
SOCIAL_GENERATION_BLOCKED_FRAGMENTS = (
    "/users/",
    "读取",
    "给出文档",
    "生成第一篇",
    "如何发布",
    "workflow json",
    "acceptance matrix",
    "required_commands",
    "execution_acceptance_steps",
    "raw agent output",
)


class SocialPublishError(RuntimeError):
    """Safe, bounded error raised when external publishing fails."""

    def __init__(self, kind: str, summary: str) -> None:
        super().__init__(summary)
        self.kind = kind
        self.summary = summary


@dataclass(frozen=True)
class XPublishResult:
    post_id: str
    response_summary: dict[str, Any]


@dataclass(frozen=True)
class GeneratedXPost:
    title: str
    body_text: str
    context_sources: tuple[str, ...] = ()
    model: str | None = None


def _json_loads(raw: str | None, fallback: Any) -> Any:
    try:
        if not raw:
            return fallback
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _bounded_excerpt(value: str, *, max_chars: int = 1000) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}... [Truncated]"


def _read_context_file(path: Path, *, max_chars: int, required: bool = False) -> str:
    if not path.is_file():
        if required:
            raise ValueError(f"agent_generation_config_error: required context file missing: {path.name}")
        return ""
    return _bounded_excerpt(path.read_text(encoding="utf-8", errors="replace"), max_chars=max_chars)


def _normalize_for_copy_check(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _sanitize_operator_prompt_for_generation(prompt: str) -> str:
    """Keep user intent while removing local paths that can confuse Codex cwd resolution."""

    text = str(prompt or "").strip()
    text = re.sub(r"/Users/[A-Za-z0-9._/\-]+", "[internal docs path omitted]", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _parse_generated_x_post(raw_text: str) -> GeneratedXPost:
    raw = str(raw_text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise ValueError("agent_generation_failed: Agent did not return JSON title/body_text") from exc
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as nested_exc:
            raise ValueError("agent_generation_failed: Agent returned invalid JSON") from nested_exc
    title = str(data.get("title") or "").strip()
    body_text = str(data.get("body_text") or data.get("body") or "").strip()
    if not title or not body_text:
        raise ValueError("agent_generation_failed: Agent response must include title and body_text")
    return GeneratedXPost(title=_bounded_excerpt(title, max_chars=140), body_text=body_text)


def _looks_like_prompt_copy(prompt: str, body_text: str) -> bool:
    prompt_normalized = _normalize_for_copy_check(prompt)
    body_normalized = _normalize_for_copy_check(body_text)
    if not prompt_normalized or not body_normalized:
        return False
    if prompt_normalized == body_normalized:
        return True
    if len(prompt_normalized) >= 80 and prompt_normalized[:160] in body_normalized:
        return True
    return any(fragment in body_normalized for fragment in SOCIAL_GENERATION_BLOCKED_FRAGMENTS)


def _prompt_needs_launch_context(prompt: str) -> bool:
    normalized = _normalize_for_copy_check(prompt)
    launch_terms = (
        "staging",
        "launch",
        "发布",
        "上线",
        "release",
        "product update",
        "feature",
        "正式",
    )
    return any(term in normalized for term in launch_terms)


def _build_social_generation_prompt(prompt: str) -> tuple[str, str, tuple[str, ...]]:
    root = config.PROJECT_ROOT
    product_context = _read_context_file(
        root / ".agents" / "product-marketing-context.md",
        max_chars=SOCIAL_CONTEXT_MAX_CHARS,
        required=True,
    )
    social_skill = _read_context_file(
        root / ".agents" / "skills" / "social-content" / "SKILL.md",
        max_chars=SOCIAL_SKILL_MAX_CHARS,
        required=True,
    )
    context_sources = ["product-marketing-context", "social-content"]
    launch_context = ""
    if _prompt_needs_launch_context(prompt):
        launch_context = _read_context_file(
            root / ".agents" / "skills" / "launch-strategy" / "SKILL.md",
            max_chars=SOCIAL_LAUNCH_SKILL_MAX_CHARS,
            required=True,
        )
        context_sources.append("launch-strategy")

    system_prompt = (
        "You are the dedicated Social Publishing copy agent for Synapse Network. "
        "Return JSON only with exactly these keys: title, body_text. "
        "Write one official X post. body_text must be <= 280 characters. "
        "Do not copy the operator prompt. Do not mention internal files, local paths, prompts, skills, workflow JSON, acceptance matrices, or implementation instructions. "
        "Do not publish, schedule, delete, or call external APIs. You only draft copy for human review."
    )
    context_block = "\n\n".join(
        part
        for part in [
            "# Product marketing context\n" + product_context,
            "# Social-content skill guidance\n" + social_skill,
            ("# Launch-strategy lightweight guidance\n" + launch_context) if launch_context else "",
        ]
        if part
    )
    safe_operator_goal = _sanitize_operator_prompt_for_generation(prompt)
    user_prompt = (
        "# Context packs for this X draft\n"
        f"{context_block}\n\n"
        "Create a concise public X draft from this operator goal. "
        "Use the context above to explain Synapse Network clearly. "
        "If the operator includes internal instructions such as reading local docs, convert them into public-facing product meaning and omit the instruction itself.\n\n"
        f"Operator goal:\n{safe_operator_goal}"
    )
    return system_prompt, user_prompt, tuple(context_sources)


def _validate_generated_x_post(prompt: str, generated: GeneratedXPost) -> None:
    combined = f"{generated.title}\n{generated.body_text}"
    normalized = _normalize_for_copy_check(combined)
    if _looks_like_prompt_copy(prompt, generated.body_text):
        raise ValueError("agent_generation_low_transform: Agent copied the prompt instead of writing a public X post")
    if len(generated.body_text) > 280:
        raise ValueError("agent_generation_failed: Agent response exceeded X 280 character limit")
    if any(fragment in normalized for fragment in SOCIAL_GENERATION_BLOCKED_FRAGMENTS):
        raise ValueError("agent_generation_failed: Agent leaked internal prompt, path, or workflow language")
    if re.search(r"/(?:Users|home|workspace|tmp)/[A-Za-z0-9._/\-]*Synapse-Network[A-Za-z0-9._/\-]*", combined, flags=re.IGNORECASE):
        raise ValueError("agent_generation_failed: Agent leaked an internal repository path")


def _is_codex_model_compatibility_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        config.SOCIAL_CONTENT_LLM_PROVIDER == "codex"
        and (
            "not supported when using codex with a chatgpt account" in message
            or "requires a newer version of codex" in message
        )
    )


def _generate_x_post_copy(prompt: str) -> GeneratedXPost:
    system_prompt, user_prompt, context_sources = _build_social_generation_prompt(prompt)
    try:
        provider = get_provider(config.SOCIAL_CONTENT_LLM_PROVIDER)
        model = config.SOCIAL_CONTENT_LLM_MODEL
        timeout = min(int(config.SOCIAL_CONTENT_LLM_TIMEOUT or 60), 60)
        try:
            raw_text, _tokens = provider.call(system_prompt, user_prompt, model, 0.2, timeout)
        except Exception as exc:
            fallback_model = str(getattr(config, "SOCIAL_CONTENT_LLM_FALLBACK_MODEL", "") or "").strip()
            if not fallback_model or fallback_model == model or not _is_codex_model_compatibility_error(exc):
                raise
            raw_text, _tokens = provider.call(system_prompt, user_prompt, fallback_model, 0.2, timeout)
            model = fallback_model
    except Exception as exc:
        raise ValueError(f"agent_generation_failed: {_bounded_excerpt(str(exc), max_chars=240)}") from exc
    generated = _parse_generated_x_post(raw_text)
    generated = GeneratedXPost(
        title=generated.title,
        body_text=generated.body_text,
        context_sources=context_sources,
        model=model,
    )
    _validate_generated_x_post(prompt, generated)
    return generated


def _safe_event_payload(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(payload or {})
    for key in list(data.keys()):
        if "token" in key.lower() or "authorization" in key.lower() or "secret" in key.lower():
            data[key] = "[redacted]"
    return data


def run_content_policy_check(body_text: str) -> dict[str, Any]:
    """Deterministic v1 content policy check for a single X post."""

    text = str(body_text or "").strip()
    blocked: list[str] = []
    warnings: list[str] = []
    if not text:
        blocked.append("body_text_empty")
    if len(text) > 280:
        blocked.append("x_post_exceeds_280_characters")
    risky_patterns = {
        "guaranteed_return": r"\b(guaranteed|guarantee|guaranteed profit|risk[- ]?free return)\b",
        "investment_advice": r"\b(investment advice|financial advice|buy now|100x|risk free)\b",
        "funds_or_secret_request": r"\b(seed phrase|private key|send funds|transfer usdc|wallet password)\b",
    }
    for key, pattern in risky_patterns.items():
        if re.search(pattern, text, flags=re.IGNORECASE):
            blocked.append(key)
    if re.search(r"\b(soon|launching|beta|waitlist)\b", text, flags=re.IGNORECASE):
        warnings.append("time_sensitive_claim_review")
    return {
        "status": "blocked" if blocked else "passed",
        "character_count": len(text),
        "warnings": warnings,
        "blocked_reasons": blocked,
    }


def _account_out(row: SocialAccountRow) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "platform": row.platform,
        "handle": row.handle,
        "display_name": row.display_name,
        "secret_ref": row.secret_ref,
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _event_out(row: SocialPublishEventRow) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "post_id": int(row.post_id),
        "event_type": row.event_type,
        "actor": row.actor,
        "summary": row.summary,
        "payload": _json_loads(row.payload_json, {}),
        "created_at": row.created_at,
    }


def _post_out(row: SocialPostDraftRow) -> SocialPostDraftOut:
    account = row.account
    events = sorted(getattr(row, "events", []) or [], key=lambda event: int(event.id or 0))
    external_url = f"https://x.com/{account.handle}/status/{row.external_post_id}" if account and row.external_post_id else None
    return SocialPostDraftOut(
        id=int(row.id),
        platform=row.platform,
        account_id=int(row.account_id),
        account_handle=account.handle if account else None,
        account_display_name=account.display_name if account else None,
        title=row.title,
        body_text=row.body_text,
        status=row.status,
        generated_by=row.generated_by,
        reviewed_by=row.reviewed_by,
        review_note=row.review_note,
        target_audience=row.target_audience,
        cta=row.cta,
        agent_rationale=row.agent_rationale,
        policy_check=_json_loads(row.policy_check_json, {}),
        raw_agent_output=_json_loads(row.raw_agent_output_json, {}),
        published_at=row.published_at,
        external_post_id=row.external_post_id,
        external_url=external_url,
        failure_summary=row.failure_summary,
        events=[_event_out(event) for event in events],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _record_event(
    db: Session,
    post: SocialPostDraftRow,
    event_type: str,
    *,
    actor: str = "operator",
    summary: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    db.add(
        SocialPublishEventRow(
            post_id=int(post.id),
            event_type=event_type,
            actor=actor or "operator",
            summary=_bounded_excerpt(summary or ""),
            payload_json=_json_dumps(_safe_event_payload(payload)),
        )
    )


def ensure_default_social_account(db: Session) -> SocialAccountRow:
    row = (
        db.query(SocialAccountRow)
        .filter(SocialAccountRow.platform == "x", SocialAccountRow.handle == DEFAULT_X_HANDLE)
        .one_or_none()
    )
    if row is not None:
        return row
    row = SocialAccountRow(
        platform="x",
        handle=DEFAULT_X_HANDLE,
        display_name="Synapse Network",
        secret_ref=DEFAULT_X_SECRET_REF,
        status="active",
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent page loads call accounts/posts in parallel. If another
        # request inserted the default account first, recover idempotently.
        db.rollback()
        row = (
            db.query(SocialAccountRow)
            .filter(SocialAccountRow.platform == "x", SocialAccountRow.handle == DEFAULT_X_HANDLE)
            .one_or_none()
        )
        if row is None:
            raise
        return row
    db.refresh(row)
    return row


def list_social_accounts(db: Session) -> list[dict[str, Any]]:
    ensure_default_social_account(db)
    rows = db.query(SocialAccountRow).order_by(SocialAccountRow.platform.asc(), SocialAccountRow.handle.asc()).all()
    return [_account_out(row) for row in rows]


def _get_post(db: Session, post_id: int) -> SocialPostDraftRow:
    row = db.get(SocialPostDraftRow, post_id)
    if row is None:
        raise ValueError("social post draft not found")
    return row


def _get_account(db: Session, account_id: int | None) -> SocialAccountRow:
    if account_id is None:
        return ensure_default_social_account(db)
    row = db.get(SocialAccountRow, account_id)
    if row is None:
        raise ValueError("social account not found")
    if row.platform != "x":
        raise ValueError("only X social accounts are supported in v1")
    if row.status != "active":
        raise ValueError("social account is not active")
    return row


def list_social_posts(db: Session, *, status: str | None = None) -> list[SocialPostDraftOut]:
    ensure_default_social_account(db)
    query = db.query(SocialPostDraftRow).order_by(SocialPostDraftRow.updated_at.desc(), SocialPostDraftRow.id.desc())
    if status:
        query = query.filter(SocialPostDraftRow.status == status)
    return [_post_out(row) for row in query.all()]


def create_social_post(db: Session, body: SocialPostCreateRequest) -> SocialPostDraftOut:
    if body.platform != "x":
        raise ValueError("only X is supported in social publishing v1")
    status = str(body.status or "needs_review").strip()
    if status not in {"draft", "needs_review", "approved"}:
        raise ValueError("new social posts can only start as draft, needs_review, or approved")
    account = _get_account(db, body.account_id)
    policy = run_content_policy_check(body.body_text)
    if status == "approved" and policy["status"] != "passed":
        raise ValueError("blocked social content cannot be approved")
    row = SocialPostDraftRow(
        platform="x",
        account_id=int(account.id),
        title=body.title,
        body_text=body.body_text.strip(),
        status=status,
        generated_by=body.generated_by or "operator",
        target_audience=body.target_audience,
        cta=body.cta,
        agent_rationale=body.agent_rationale,
        policy_check_json=_json_dumps(policy),
        raw_agent_output_json=_json_dumps(body.raw_agent_output),
    )
    db.add(row)
    db.flush()
    _record_event(
        db,
        row,
        "draft_created",
        actor=body.generated_by or "operator",
        summary="Social post draft created; no external publish attempted.",
        payload={"policy_status": policy["status"]},
    )
    db.commit()
    db.refresh(row)
    return _post_out(row)


def generate_social_post_draft(db: Session, body: SocialPostGenerateDraftRequest) -> SocialPostDraftOut:
    """Create a publish-ready X draft from an operator prompt when policy passes."""

    prompt = str(body.prompt or "").strip()
    if not prompt:
        raise ValueError("prompt is required for Agent draft generation")
    if len(prompt) > 1200:
        raise ValueError("prompt is too long for v1 Agent draft generation")
    account = _get_account(db, body.account_id)
    generated = _generate_x_post_copy(prompt)
    policy = run_content_policy_check(generated.body_text)
    generated_status = "approved" if policy["status"] == "passed" else "needs_review"
    row = SocialPostDraftRow(
        platform="x",
        account_id=int(account.id),
        title=generated.title,
        body_text=generated.body_text,
        status=generated_status,
        generated_by="social_content_agent_v1",
        reviewed_by=(body.actor or "operator") if generated_status == "approved" else None,
        target_audience=None,
        cta=None,
        agent_rationale=None,
        policy_check_json=_json_dumps(policy),
        raw_agent_output_json=_json_dumps(
            {
                "source": "llm_social_content_agent_v1",
                "provider": config.SOCIAL_CONTENT_LLM_PROVIDER,
                "requested_model": config.SOCIAL_CONTENT_LLM_MODEL,
                "model": generated.model or config.SOCIAL_CONTENT_LLM_MODEL,
                "context_sources": list(generated.context_sources),
                "media_support": "text_only_v1",
            }
        ),
    )
    db.add(row)
    db.flush()
    _record_event(
        db,
        row,
        "agent_draft_generated",
        actor=body.actor or "operator",
        summary="Agent generated an X draft from operator prompt; no external publish attempted.",
        payload={
            "policy_status": policy["status"],
            "generated_status": generated_status,
            "prompt_excerpt": _bounded_excerpt(prompt, max_chars=240),
        },
    )
    db.commit()
    db.refresh(row)
    return _post_out(row)


def update_social_post(db: Session, post_id: int, body: SocialPostPatchRequest) -> SocialPostDraftOut:
    row = _get_post(db, post_id)
    if row.status == "published":
        raise ValueError("published X posts cannot be edited by this system")
    if body.status and body.status not in ALLOWED_STATUSES:
        raise ValueError("unsupported social post status")
    if body.status in {"publishing", "published", "failed"}:
        raise ValueError("publishing states are controlled by publish-x")

    changed_body = body.body_text is not None and body.body_text.strip() != row.body_text
    if body.title is not None:
        row.title = body.title
    if body.body_text is not None:
        row.body_text = body.body_text.strip()
    if body.target_audience is not None:
        row.target_audience = body.target_audience
    if body.cta is not None:
        row.cta = body.cta
    if body.agent_rationale is not None:
        row.agent_rationale = body.agent_rationale
    if body.review_note is not None:
        row.review_note = body.review_note

    policy = run_content_policy_check(row.body_text)
    row.policy_check_json = _json_dumps(policy)
    if body.status == "approved":
        if policy["status"] != "passed":
            raise ValueError("blocked social content cannot be approved")
        row.status = "approved"
        row.reviewed_by = body.reviewed_by or "operator"
        row.failure_summary = None
        event_type = "approved"
        summary = "Human approved draft for X publishing."
    elif body.status == "rejected":
        row.status = "rejected"
        row.reviewed_by = body.reviewed_by or "operator"
        event_type = "rejected"
        summary = "Human rejected social draft."
    elif body.status in {"draft", "needs_review"}:
        row.status = body.status
        event_type = "status_updated"
        summary = f"Draft moved to {body.status}."
    else:
        if changed_body and row.status == "approved":
            row.status = "needs_review"
        event_type = "edited"
        summary = "Draft content edited."

    _record_event(db, row, event_type, actor=body.reviewed_by or "operator", summary=summary, payload={"policy_status": policy["status"]})
    db.commit()
    db.refresh(row)
    return _post_out(row)


def request_social_post_rewrite(db: Session, post_id: int, body: SocialPostRewriteRequest) -> SocialPostDraftOut:
    row = _get_post(db, post_id)
    if row.status in HUMAN_SETTLED_STATUSES:
        raise ValueError("settled social posts cannot request rewrite")
    row.status = "needs_review"
    row.review_note = body.feedback or row.review_note
    _record_event(
        db,
        row,
        "rewrite_requested",
        actor=body.actor,
        summary="Operator requested an Agent rewrite. v1 records the request; publishing remains human-gated.",
        payload={"feedback": body.feedback or ""},
    )
    db.commit()
    db.refresh(row)
    return _post_out(row)


class XApiPublisher:
    """Narrow adapter for X API publishing.

    Tests replace this object; production reads Secret Manager only at publish time.
    """

    def publish_text(self, account: SocialAccountRow, body_text: str) -> XPublishResult:
        token = _read_secret_token(account.secret_ref)
        payload = json.dumps({"text": body_text}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            X_POST_URL,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed X API endpoint
                raw = response.read(8192).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read(4096).decode("utf-8", errors="replace")
            if exc.code in {401, 403}:
                raise SocialPublishError("x_auth_failed", "X API authentication failed. Update the OAuth user token secret.") from exc
            if exc.code == 429:
                raise SocialPublishError("x_rate_limited", "X API rate limit reached. Try again after the rate-limit window.") from exc
            raise SocialPublishError("x_api_failed", f"X API returned HTTP {exc.code}: {_bounded_excerpt(raw)}") from exc
        except Exception as exc:  # pragma: no cover - network/credential dependent
            raise SocialPublishError("x_api_failed", f"X publish request failed: {_bounded_excerpt(str(exc))}") from exc
        data = _json_loads(raw, {})
        post_id = str(((data.get("data") if isinstance(data, dict) else {}) or {}).get("id") or "").strip()
        if not post_id:
            raise SocialPublishError("x_api_failed", "X API response did not include a post id.")
        return XPublishResult(post_id=post_id, response_summary={"data": {"id": post_id}})


def _read_secret_token(secret_ref: str) -> str:
    ref = str(secret_ref or "").strip()
    if not ref:
        raise SocialPublishError("x_auth_failed", "X credential secret reference is empty.")
    if ref.startswith("env:"):
        value = os.environ.get(ref.removeprefix("env:"), "")
        if not value:
            raise SocialPublishError("x_auth_failed", "X credential environment variable is missing.")
        return value
    try:
        from google.cloud import secretmanager  # type: ignore
    except Exception as exc:  # pragma: no cover - optional production dependency
        raise SocialPublishError("x_auth_failed", "Google Secret Manager client is unavailable in this runtime.") from exc
    project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("STAGING_GCP_PROJECT_ID")
    if not project_id and not ref.startswith("projects/"):
        raise SocialPublishError("x_auth_failed", "GCP project id is required to read the X credential secret.")
    secret_name = ref if ref.startswith("projects/") else f"projects/{project_id}/secrets/{ref}/versions/latest"
    try:
        response = secretmanager.SecretManagerServiceClient().access_secret_version(request={"name": secret_name})
    except Exception as exc:  # pragma: no cover - credential dependent
        raise SocialPublishError("x_auth_failed", f"Secret Manager read failed: {_bounded_excerpt(str(exc))}") from exc
    token = response.payload.data.decode("utf-8", errors="replace").strip()
    if not token:
        raise SocialPublishError("x_auth_failed", "X credential secret is empty.")
    return token


x_publisher: XApiPublisher = XApiPublisher()


def publish_social_post_to_x(db: Session, post_id: int, body: SocialPostPublishRequest) -> SocialPostDraftOut:
    row = _get_post(db, post_id)
    if row.platform != "x":
        raise ValueError("only X publishing is supported in v1")
    if row.status != "approved":
        raise ValueError("only approved social drafts can be published to X")
    policy = run_content_policy_check(row.body_text)
    row.policy_check_json = _json_dumps(policy)
    if policy["status"] != "passed":
        raise ValueError("blocked social content cannot be published")
    row.status = "publishing"
    row.failure_summary = None
    _record_event(db, row, "publish_requested", actor=body.actor, summary="Human requested X publish.")
    db.commit()
    db.refresh(row)
    try:
        result = x_publisher.publish_text(row.account, row.body_text)
    except SocialPublishError as exc:
        row.status = "failed"
        row.failure_summary = exc.summary
        _record_event(
            db,
            row,
            "publish_failed",
            actor=body.actor,
            summary=exc.summary,
            payload={"root_cause_kind": exc.kind},
        )
        db.commit()
        db.refresh(row)
        return _post_out(row)

    row.status = "published"
    row.external_post_id = result.post_id
    row.published_at = utcnow()
    row.reviewed_by = row.reviewed_by or body.actor
    _record_event(
        db,
        row,
        "published",
        actor=body.actor,
        summary=f"Published to X as post {result.post_id}.",
        payload={"external_post_id": result.post_id, "response_summary": result.response_summary},
    )
    db.commit()
    db.refresh(row)
    return _post_out(row)
