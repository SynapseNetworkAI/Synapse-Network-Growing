"""Social publishing service with human-gated X posting."""

from __future__ import annotations

import json
import logging
import base64
import contextvars
import hashlib
import mimetypes
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from server import config
from server.database import (
    SessionLocal,
    SocialAccountRow,
    SocialCampaignGoalRow,
    SocialOAuthSessionRow,
    SocialPostDraftRow,
    SocialPostMediaAssetRow,
    SocialPostMetricRow,
    SocialPublishEventRow,
    SocialReplyItemRow,
    SocialRepostCandidateRow,
    SocialTrendItemRow,
    SocialWatchlistAccountRow,
    utcnow,
)
from server.schemas import (
    SocialCampaignGoalCreateRequest,
    SocialCampaignGoalOut,
    SocialOpsOverviewOut,
    SocialPostCreateRequest,
    SocialPostDraftOut,
    SocialPostGenerateDraftRequest,
    SocialPostMetricOut,
    SocialPostPatchRequest,
    SocialPostPublishRequest,
    SocialPostRewriteRequest,
    SocialReplyPatchRequest,
    SocialReplyPublishRequest,
    SocialRepostPublishRequest,
    SocialXOAuthCallbackOut,
    SocialXOAuthStartOut,
    SocialReplyItemOut,
    SocialRepostCandidateOut,
    SocialTrendQueryOut,
    SocialTrendItemOut,
    SocialWatchlistAccountOut,
)
from server.services.agents.llm_adapter import get_provider
from server.services.runtime.codex_cli import CodexExecResult, filter_codex_stderr, run_codex_exec
from server.services.social.defaults import DEFAULT_WATCHLIST_ACCOUNTS
from server.services.social.reply_agent import generate_x_reply_for_candidate
from server.services.social.reply_records import apply_generated_reply_to_row, reply_agent_failure_summary
from server.services.social.x_client import XApiAuthError, XApiClient, XApiRateLimitError, XApiTransientError, XPost

DEFAULT_X_HANDLE = "SynapseNetworkA"
DEFAULT_X_SECRET_REF = "x-official"
X_POST_URL = "https://api.x.com/2/tweets"
X_MEDIA_UPLOAD_URL = "https://api.x.com/2/media/upload"
X_OAUTH_AUTHORIZE_URL = "https://twitter.com/i/oauth2/authorize"
X_OAUTH_TOKEN_URL = "https://api.x.com/2/oauth2/token"
X_OAUTH_SCOPE = "tweet.read tweet.write users.read media.write offline.access"
logger = logging.getLogger("ops-dashboard.social-publishing")
_x_publish_access_token: contextvars.ContextVar[str | None] = contextvars.ContextVar("x_publish_access_token", default=None)
ALLOWED_STATUSES = {"draft", "generating", "needs_review", "approved", "publishing", "published", "failed", "rejected"}
HUMAN_SETTLED_STATUSES = {"published", "rejected"}
SOCIAL_CONTEXT_MAX_CHARS = 1100
SOCIAL_SKILL_MAX_CHARS = 900
SOCIAL_LAUNCH_SKILL_MAX_CHARS = 600
SOCIAL_GENERATION_BLOCKED_FRAGMENTS = (
    "/users/",
    "api-key",
    "authorization:",
    "bearer token",
    "private key",
    "secret token",
    "workflow json",
    "acceptance matrix",
    "required_commands",
    "execution_acceptance_steps",
    "raw agent output",
)
SOCIAL_STYLE_TYPES = {"marketing", "technical", "visionary"}
SOCIAL_MEDIA_MODES = {"auto", "text_only", "image_required"}
SOCIAL_MEDIA_DECISIONS = {"text", "image"}
SOCIAL_CODEX_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 1},
        "body_text": {"type": "string", "minLength": 1},
        "media_decision": {"type": "string", "enum": ["text", "image"]},
        "image_prompt": {"type": "string"},
        "image_alt_text": {"type": "string"},
    },
    "required": ["title", "body_text", "media_decision", "image_prompt", "image_alt_text"],
}

class SocialPublishError(RuntimeError):
    """Safe, bounded error raised when external publishing fails."""

    def __init__(self, kind: str, summary: str) -> None:
        super().__init__(summary)
        self.kind = kind
        self.summary = summary


def _is_gcp_adc_reauth_error(value: object) -> bool:
    text = str(value or "").lower()
    return "reauthentication is needed" in text or "application-default login" in text


def _gcp_adc_reauth_summary() -> str:
    return "Local Google credentials expired. Run `gcloud auth application-default login` and refresh /publishing."


@dataclass(frozen=True)
class XPublishResult:
    post_id: str
    response_summary: dict[str, Any]


@dataclass(frozen=True)
class GeneratedXPost:
    title: str
    body_text: str
    media_decision: str = "text"
    image_prompt: str | None = None
    image_alt_text: str | None = None
    context_sources: tuple[str, ...] = ()
    model: str | None = None
    generation_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class GeneratedImageResult:
    local_path: str
    preview_url: str


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


def _parse_generated_x_post(raw_text: str) -> GeneratedXPost:
    raw = str(raw_text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        json_object = _extract_first_json_object(raw)
        if not json_object:
            raise ValueError("agent_generation_failed: Agent did not return JSON title/body_text") from exc
        try:
            data = json.loads(json_object)
        except json.JSONDecodeError as nested_exc:
            raise ValueError("agent_generation_failed: Agent returned invalid JSON") from nested_exc
    title = str(data.get("title") or "").strip()
    body_text = str(data.get("body_text") or data.get("body") or "").strip()
    media_decision = str(data.get("media_decision") or "text").strip().lower()
    image_prompt = str(data.get("image_prompt") or "").strip()
    image_alt_text = str(data.get("image_alt_text") or "").strip()
    if not title or not body_text:
        raise ValueError("agent_generation_failed: Agent response must include title and body_text")
    if media_decision not in SOCIAL_MEDIA_DECISIONS:
        media_decision = "text"
    return GeneratedXPost(
        title=_bounded_excerpt(title, max_chars=140),
        body_text=body_text,
        media_decision=media_decision,
        image_prompt=image_prompt or None,
        image_alt_text=image_alt_text or None,
    )


def _extract_first_json_object(raw: str) -> str | None:
    """Extract the first balanced JSON object from model output."""

    text = str(raw or "")
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        start = text.find("{", start + 1)
    return None


def _looks_like_prompt_copy(prompt: str, body_text: str) -> bool:
    prompt_normalized = _normalize_for_copy_check(prompt)
    body_normalized = _normalize_for_copy_check(body_text)
    if not prompt_normalized or not body_normalized:
        return False
    if prompt_normalized == body_normalized:
        return True
    return len(prompt_normalized) >= 80 and prompt_normalized[:160] in body_normalized


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

def _sanitize_operator_prompt_for_generation(prompt: str) -> str:
    """Redact sensitive local paths without deleting the operator's intent."""

    text = str(prompt or "").strip()
    text = re.sub(r"/Users/[A-Za-z0-9._/\-]+", "[path]", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_style_type(style_type: str | None) -> str:
    normalized = str(style_type or "").strip().lower()
    return normalized if normalized in SOCIAL_STYLE_TYPES else "marketing"


def _normalize_media_mode(media_mode: str | None) -> str:
    normalized = str(media_mode or "").strip().lower()
    return normalized if normalized in SOCIAL_MEDIA_MODES else "auto"


def _style_guidance(style_type: str) -> str:
    if style_type == "technical":
        return "Emphasize concrete infrastructure, developer workflow, API/provider utility, and credible technical detail."
    if style_type == "visionary":
        return "Emphasize the agent economy, M2M commerce, why this shift matters, and the long-term category narrative."
    return "Emphasize clear product value, trust, adoption, and why builders should care now."


def _media_guidance(media_mode: str) -> str:
    if media_mode == "text_only":
        return "Do not request media. Set media_decision to text and leave image_prompt/image_alt_text empty."
    if media_mode == "image_required":
        return "Include one image. Set media_decision to image and provide a concise image_prompt plus image_alt_text."
    return (
        "Decide if one image would materially improve clarity or brand trust. "
        "Use media_decision=image for a useful visual; otherwise use media_decision=text."
    )


def _build_social_generation_prompt(
    prompt: str,
    *,
    style_type: str | None = None,
    media_mode: str | None = None,
) -> tuple[str, str, tuple[str, ...], str, str]:
    root = config.PROJECT_ROOT
    normalized_style = _normalize_style_type(style_type)
    normalized_media_mode = _normalize_media_mode(media_mode)
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
        "You are the Synapse Network X Social Media Manager. "
        "Your job is to write compelling, high-trust X content that helps developers, AI agent builders, "
        "API providers, and early operators understand what Synapse Network does and why it matters. "
        "Write with a strong hook, clear product value, and credible technical authority. "
        "Make the post engaging enough for X: concrete, benefit-led, and easy to share. "
        "Default to a substantial X Premium-style post when the operator provides enough context: "
        "multiple short paragraphs, useful detail, and enough explanation to build trust. "
        "Do not make it short unless the operator explicitly asks for a short post. "
        "Explain user-facing benefits, not internal implementation details. "
        "If the operator prompt contains instructions like 'read docs', 'how to publish', or local paths, "
        "treat them as background intent and convert them into public-facing product meaning. "
        "Do not expose internal paths, workflow JSON, secrets, acceptance matrices, or private implementation details. "
        "When media is useful, write a safe image prompt for a polished SaaS/AI infrastructure visual. "
        "The image prompt must not include local paths, secrets, private deployment details, financial return promises, or text that must be exactly rendered. "
        "End body_text with 2-4 relevant X hashtags. Prefer tags such as #AIAgents, #AgentEconomy, #APIs, #Micropayments, #DeveloperTools, or #MachinePayments when they fit. "
        "Tone: technical but accessible, forward-thinking, confident, trustworthy, and readable. "
        "Return JSON only: {'title': '...', 'body_text': '...', 'media_decision': 'text|image', 'image_prompt': '...', 'image_alt_text': '...'}."
    )

    context_block = "\n\n".join(
        part for part in [
            "# Product marketing context\n" + product_context,
            "# Social-content skill guidance\n" + social_skill,
            ("# Launch-strategy lightweight guidance\n" + launch_context) if launch_context else "",
        ] if part
    )

    safe_operator_goal = _sanitize_operator_prompt_for_generation(prompt)
    user_prompt = (
        f"# Context packs\n{context_block}\n\n"
        f"# Style mode\n{normalized_style}: {_style_guidance(normalized_style)}\n\n"
        f"# Media mode\n{normalized_media_mode}: {_media_guidance(normalized_media_mode)}\n\n"
        "--- TASK ---\n"
        "Write an engaging X post based on the operator's goal. "
        "Start with a strong hook, explain the public product benefit, and make the post worth reading or sharing. "
        "Prefer a complete X Premium post with several compact paragraphs when there is enough material. "
        "Do not optimize for the old 280-character tweet format. "
        "Finish the post with 2-4 natural hashtags that match the topic; do not use generic spammy tags. "
        "If the goal contains instructions like 'read docs', 'how to publish', or 'generate the first post', "
        "do not copy those instructions; translate them into product context and audience value.\n\n"
        f"Operator goal:\n{safe_operator_goal}"
    )
    return system_prompt, user_prompt, tuple(context_sources), normalized_style, normalized_media_mode


def _validate_generated_x_post(prompt: str, generated: GeneratedXPost) -> None:
    combined = f"{generated.title}\n{generated.body_text}\n{generated.image_prompt or ''}\n{generated.image_alt_text or ''}"
    normalized = _normalize_for_copy_check(combined)
    if _looks_like_prompt_copy(prompt, generated.body_text):
        raise ValueError("agent_generation_low_transform: Agent copied the prompt instead of writing a public X post")
    if any(fragment in normalized for fragment in SOCIAL_GENERATION_BLOCKED_FRAGMENTS):
        raise ValueError("agent_generation_failed: Agent leaked internal prompt, path, or workflow language")
    if re.search(r"\b(api[_-]?key|token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9._\-]{12,}", combined, flags=re.IGNORECASE):
        raise ValueError("agent_generation_failed: Agent leaked credential-shaped text")
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


def _social_codex_prompt(system_prompt: str, user_prompt: str) -> str:
    return (
        "# Role\n"
        "You are the Synapse Network Social Publishing copy agent.\n\n"
        "# System constraints\n"
        f"{system_prompt}\n\n"
        "# Task context\n"
        f"{user_prompt}\n\n"
        "# Required output\n"
        "Return only valid JSON matching this exact schema:\n"
        '{"title":"public X content title","body_text":"public X post text","media_decision":"text","image_prompt":"","image_alt_text":""}\n'
        "No markdown fences. No explanation. No extra keys."
    )


def _codex_output_path() -> Path:
    out_dir = config.PROJECT_ROOT / "runtime" / "social-publishing-codex"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{uuid.uuid4().hex}-draft.json"


def _codex_failure_detail(result: CodexExecResult, *, model: str | None) -> str:
    stderr = filter_codex_stderr(result.stderr, max_lines=8) or result.stderr
    stdout = result.stdout or result.text
    return (
        "agent_generation_failed: codex_cli_failed "
        f"provider=codex model={model or '(default)'} exit_code={result.exit_code} "
        f"output_artifact={str(result.output_path) if result.output_path else '-'} "
        f"stderr={_bounded_excerpt(stderr or '-', max_chars=520)} "
        f"stdout={_bounded_excerpt(stdout or '-', max_chars=360)}"
    )


def _codex_nonzero_can_use_json(result: CodexExecResult) -> bool:
    """Accept non-zero Codex only when useful JSON exists.

    Codex occasionally exits non-zero after producing the last message because of
    local cleanup/plugin stderr, timeout-after-output, or process teardown noise.
    Business validation still happens afterwards, so invalid/unsafe JSON remains
    fail-closed.
    """

    if result.exit_code == 0:
        return True
    if not str(result.text or "").strip():
        return False
    try:
        _parse_generated_x_post(result.text)
    except ValueError:
        return False
    return True


def _is_codex_cli_model_compatibility_result(result: CodexExecResult) -> bool:
    message = f"{result.stdout}\n{result.stderr}\n{result.text}".lower()
    return (
        "requires a newer version of codex" in message
        or "not supported when using codex with a chatgpt account" in message
    )


def _social_codex_fallback_models(primary_model: str) -> list[str]:
    raw = str(getattr(config, "SOCIAL_CONTENT_LLM_FALLBACK_MODEL", "") or "").strip()
    models: list[str] = []
    for item in re.split(r"[,\\s]+", raw):
        model = item.strip()
        if model and model != primary_model and model not in models:
            models.append(model)
    return models


def _run_social_codex_once(system_prompt: str, user_prompt: str, *, model: str, timeout: int) -> CodexExecResult:
    output_path = _codex_output_path()
    return run_codex_exec(
        prompt=_social_codex_prompt(system_prompt, user_prompt),
        cwd=config.PROJECT_ROOT,
        output_path=output_path,
        model=model,
        timeout=timeout,
        add_dirs=[config.PROJECT_ROOT],
        output_schema=SOCIAL_CODEX_OUTPUT_SCHEMA,
        sandbox_mode="read-only",
    )


def _call_social_codex(system_prompt: str, user_prompt: str, *, model: str, timeout: int) -> tuple[str, dict[str, Any], str]:
    result = _run_social_codex_once(system_prompt, user_prompt, model=model, timeout=timeout)
    used_model = model
    used_fallback = False
    attempted_models = [model]
    while result.exit_code != 0 and _is_codex_cli_model_compatibility_result(result):
        next_model = next((candidate for candidate in _social_codex_fallback_models(model) if candidate not in attempted_models), "")
        if not next_model:
            break
        result = _run_social_codex_once(system_prompt, user_prompt, model=next_model, timeout=timeout)
        used_model = next_model
        used_fallback = True
        attempted_models.append(next_model)
    metadata = {
        "provider": "codex",
        "model": used_model,
        "requested_model": model,
        "fallback_used": used_fallback,
        "attempted_models": attempted_models,
        "exit_code": int(result.exit_code),
        "output_artifact": str(result.output_path) if result.output_path else None,
        "thread_id": result.thread_id,
        "json_event_count": int(result.json_event_count or 0),
        "execution_time_ms": int(result.execution_time_ms or 0),
        "nonzero_exit_with_valid_json": bool(result.exit_code != 0 and result.text.strip()),
        "timeout_after_valid_json": bool(result.exit_code == 124 and _codex_nonzero_can_use_json(result)),
    }
    if not _codex_nonzero_can_use_json(result):
        raise ValueError(_codex_failure_detail(result, model=used_model))
    return result.text, metadata, used_model


def _generate_x_post_copy(prompt: str, *, style_type: str | None = None, media_mode: str | None = None) -> GeneratedXPost:
    system_prompt, user_prompt, context_sources, normalized_style, normalized_media_mode = _build_social_generation_prompt(
        prompt,
        style_type=style_type,
        media_mode=media_mode,
    )
    model = config.SOCIAL_CONTENT_LLM_MODEL
    generation_metadata: dict[str, Any] = {}
    timeout = min(max(int(config.SOCIAL_CONTENT_LLM_TIMEOUT or 180), 30), 900)
    retry_feedback = ""
    last_error = ""
    for attempt in range(2):
        try:
            attempt_user_prompt = user_prompt
            if retry_feedback:
                attempt_user_prompt = (
                    f"{user_prompt}\n\n"
                    "# Rewrite feedback\n"
                    f"{retry_feedback}\n"
                    "Write a transformed public-facing X post. Return strict JSON only."
                )
            if config.SOCIAL_CONTENT_LLM_PROVIDER == "codex":
                raw_text, generation_metadata, model = _call_social_codex(
                    system_prompt,
                    attempt_user_prompt,
                    model=model,
                    timeout=timeout,
                )
            else:
                provider = get_provider(config.SOCIAL_CONTENT_LLM_PROVIDER)
                raw_text, _tokens = provider.call(system_prompt, attempt_user_prompt, model, 0.7 if attempt == 0 else 0.3, timeout)
        except Exception as exc:
            if str(exc).startswith("agent_generation_failed:"):
                raise
            raise ValueError(f"agent_generation_failed: {_bounded_excerpt(str(exc), max_chars=720)}") from exc
        try:
            generated = _parse_generated_x_post(raw_text)
        except ValueError as exc:
            last_error = str(exc)
            if attempt == 0:
                retry_feedback = (
                    f"The previous response was not valid JSON for title/body_text: {_bounded_excerpt(raw_text, max_chars=700)}. "
                    "Convert the useful public-facing content into the required JSON schema. "
                    "Do not include markdown fences, commentary, or extra keys."
                )
                continue
            raise ValueError(f"{last_error}; raw_excerpt={_bounded_excerpt(raw_text, max_chars=700)}") from exc
        generated = GeneratedXPost(
            title=generated.title,
            body_text=generated.body_text,
            media_decision="text" if normalized_media_mode == "text_only" else generated.media_decision,
            image_prompt=generated.image_prompt,
            image_alt_text=generated.image_alt_text,
            context_sources=context_sources,
            model=model,
            generation_metadata={
                **generation_metadata,
                "style_type": normalized_style,
                "media_mode": normalized_media_mode,
                "rewrite_attempted": bool(attempt),
            },
        )
        if normalized_media_mode == "image_required":
            generated = GeneratedXPost(
                title=generated.title,
                body_text=generated.body_text,
                media_decision="image",
                image_prompt=generated.image_prompt,
                image_alt_text=generated.image_alt_text,
                context_sources=generated.context_sources,
                model=generated.model,
                generation_metadata=generated.generation_metadata,
            )
        if generated.media_decision == "image" and not generated.image_prompt:
            raise ValueError("agent_generation_failed: Agent selected image media but did not return image_prompt")
        try:
            _validate_generated_x_post(prompt, generated)
            return generated
        except ValueError as exc:
            last_error = str(exc)
            if "agent_generation_low_transform" in str(exc) and attempt == 0:
                retry_feedback = str(exc)
                continue
            raise
    raise ValueError(last_error or "agent_generation_failed: Agent could not produce transformed public X copy")


def _safe_event_payload(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(payload or {})
    for key in list(data.keys()):
        if "token" in key.lower() or "authorization" in key.lower() or "secret" in key.lower():
            data[key] = "[redacted]"
    return data


def _ensure_aware_utc(value: datetime | None) -> datetime:
    current = value or utcnow()
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _operator_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(config.OPERATOR_TIMEZONE)
    except Exception:
        return ZoneInfo("UTC")


def _operator_local_date(value: datetime | None = None) -> str:
    return _ensure_aware_utc(value).astimezone(_operator_timezone()).date().isoformat()


def run_content_policy_check(body_text: str) -> dict[str, Any]:
    """Deterministic content policy check for a human-gated X post."""

    text = str(body_text or "").strip()
    blocked: list[str] = []
    warnings: list[str] = []
    if not text:
        blocked.append("body_text_empty")
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


def _validate_image_prompt(prompt: str, alt_text: str | None = None) -> None:
    combined = f"{prompt}\n{alt_text or ''}"
    normalized = _normalize_for_copy_check(combined)
    if not str(prompt or "").strip():
        raise ValueError("image_prompt_empty")
    if any(fragment in normalized for fragment in SOCIAL_GENERATION_BLOCKED_FRAGMENTS):
        raise ValueError("image_prompt_leaked_internal_or_secret_context")
    if re.search(r"/(?:Users|home|workspace|tmp)/[A-Za-z0-9._/\-]*", combined, flags=re.IGNORECASE):
        raise ValueError("image_prompt_leaked_local_path")
    if re.search(r"\b(api[_-]?key|token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9._\-]{12,}", combined, flags=re.IGNORECASE):
        raise ValueError("image_prompt_contains_credential_shaped_text")
    if re.search(r"\b(guaranteed profit|risk[- ]?free return|100x|private key|seed phrase)\b", combined, flags=re.IGNORECASE):
        raise ValueError("image_prompt_contains_high_risk_claim")


def _media_runtime_dir() -> Path:
    path = config.PROJECT_ROOT / "runtime" / "social-publishing-media"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _image_extension(filename: str | None, content_type: str | None, payload: bytes) -> str:
    mime = str(content_type or "").lower()
    suffix = Path(str(filename or "")).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    if "png" in mime:
        return ".png"
    if "jpeg" in mime or "jpg" in mime:
        return ".jpg"
    if "webp" in mime:
        return ".webp"
    if "gif" in mime:
        return ".gif"
    if payload.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if payload[:6] in {b"GIF87a", b"GIF89a"}:
        return ".gif"
    if payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        return ".webp"
    raise ValueError("uploaded media must be an image")


def _validate_uploaded_image(filename: str | None, content_type: str | None, payload: bytes) -> str:
    if not payload:
        raise ValueError("uploaded image is empty")
    max_bytes = 8 * 1024 * 1024
    if len(payload) > max_bytes:
        raise ValueError("uploaded image exceeds 8MB")
    mime = str(content_type or "").lower()
    if mime and not mime.startswith("image/"):
        raise ValueError("uploaded media must be an image")
    return _image_extension(filename, content_type, payload)


def _safe_image_prompt_context(value: str | None, *, max_chars: int) -> str:
    text = _bounded_excerpt(str(value or "").strip(), max_chars=max_chars)
    text = re.sub(r"/Users/[A-Za-z0-9._/\-]+", "[path]", text)
    text = re.sub(r"https?://\S+", "[link]", text)
    return re.sub(r"\s+", " ", text).strip()


def _fallback_image_prompt_for_post(row: SocialPostDraftRow) -> tuple[str, str]:
    title = _safe_image_prompt_context(row.title or "Synapse Network X update", max_chars=120)
    body = _safe_image_prompt_context(row.body_text, max_chars=260)
    prompt = (
        "Create a polished, high-trust SaaS and AI infrastructure illustration for a Synapse Network official X post. "
        f"Theme: {title}. "
        f"Public message context: {body or 'AI agents, API access, payment rails, budget controls, and settlement infrastructure.'} "
        "Visualize AI agents connected to APIs through governed payment rails and settlement flows. "
        "Use a modern dark ops cockpit aesthetic with abstract network nodes, subtle cyan/green accents, no readable text, no logos, no screenshots, and no secrets."
    )
    return prompt, _bounded_excerpt(f"Synapse Network visual for {title}", max_chars=180)


def _media_preview_url(asset_id: int) -> str:
    return f"/api/social/media/{asset_id}/preview"


class SocialImageGenerator:
    """Narrow OpenAI Images adapter for one reviewable X image asset."""

    def generate_image(self, *, prompt: str, asset_id: int) -> GeneratedImageResult:
        provider = str(config.SOCIAL_IMAGE_PROVIDER or "").strip().lower()
        if provider != "openai_images":
            raise ValueError(f"image_generation_failed: unsupported provider {provider or '(empty)'}")
        api_key = str(config.OPENAI_API_KEY or "").strip()
        if not api_key:
            raise ValueError("image_generation_failed: OPENAI_API_KEY is required for openai_images")

        payload = json.dumps(
            {
                "model": config.SOCIAL_IMAGE_MODEL,
                "prompt": prompt,
                "size": "1024x1024",
                "n": 1,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://api.openai.com/v1/images/generations",
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=max(10, int(config.SOCIAL_IMAGE_TIMEOUT or 90))) as response:  # noqa: S310 - fixed OpenAI endpoint
                raw = response.read(2_000_000).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read(4096).decode("utf-8", errors="replace")
            raise ValueError(f"image_generation_failed: OpenAI Images API HTTP {exc.code}: {_bounded_excerpt(raw, max_chars=600)}") from exc
        except Exception as exc:  # pragma: no cover - external credential/network dependent
            raise ValueError(f"image_generation_failed: {_bounded_excerpt(str(exc), max_chars=600)}") from exc

        data = _json_loads(raw, {})
        image_rows = data.get("data") if isinstance(data, dict) else None
        first = image_rows[0] if isinstance(image_rows, list) and image_rows else {}
        output_path = _media_runtime_dir() / f"social-post-media-{asset_id}.png"
        if isinstance(first, dict) and first.get("b64_json"):
            try:
                output_path.write_bytes(base64.b64decode(str(first["b64_json"])))
            except Exception as exc:
                raise ValueError("image_generation_failed: OpenAI image payload was not valid base64") from exc
        elif isinstance(first, dict) and first.get("url"):
            try:
                with urllib.request.urlopen(str(first["url"]), timeout=30) as response:  # noqa: S310 - provider-returned image URL
                    output_path.write_bytes(response.read(8_000_000))
            except Exception as exc:  # pragma: no cover - provider/network dependent
                raise ValueError(f"image_generation_failed: failed to download generated image: {_bounded_excerpt(str(exc), max_chars=400)}") from exc
        else:
            raise ValueError("image_generation_failed: OpenAI Images API did not return image data")
        return GeneratedImageResult(local_path=str(output_path), preview_url=_media_preview_url(asset_id))


image_generator: SocialImageGenerator = SocialImageGenerator()


def _account_out(row: SocialAccountRow) -> dict[str, Any]:
    auth_status, auth_message = x_oauth_token_provider.auth_status()
    return {
        "id": int(row.id),
        "platform": row.platform,
        "handle": row.handle,
        "display_name": row.display_name,
        "secret_ref": row.secret_ref,
        "status": row.status,
        "auth_status": auth_status,
        "auth_message": auth_message,
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


def _media_out(row: SocialPostMediaAssetRow) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "post_id": int(row.post_id),
        "media_type": row.media_type,
        "status": row.status,
        "prompt": row.prompt,
        "alt_text": row.alt_text,
        "preview_url": row.preview_url or _media_preview_url(int(row.id)),
        "x_media_id": row.x_media_id,
        "failure_summary": row.failure_summary,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _post_out(row: SocialPostDraftRow) -> SocialPostDraftOut:
    account = row.account
    events = sorted(getattr(row, "events", []) or [], key=lambda event: int(event.id or 0))
    media_assets = sorted(getattr(row, "media_assets", []) or [], key=lambda media: int(media.id or 0))
    external_url = f"https://x.com/{account.handle}/status/{row.external_post_id}" if account and row.external_post_id else None
    return SocialPostDraftOut(
        id=int(row.id),
        platform=row.platform,
        account_id=int(row.account_id),
        source_type=getattr(row, "source_type", None) or "manual_prompt",
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
        media_assets=[_media_out(media) for media in media_assets],
        events=[_event_out(event) for event in events],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _generation_running_policy() -> dict[str, Any]:
    return {
        "status": "running",
        "character_count": 0,
        "warnings": [],
        "blocked_reasons": [],
    }


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
        if row.secret_ref == "x-official-oauth2-user-token":
            row.secret_ref = DEFAULT_X_SECRET_REF
            db.commit()
            db.refresh(row)
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


def ensure_default_social_ops_seed(db: Session) -> None:
    """Seed safe, human-gated social ops examples without touching X."""

    if db.query(SocialCampaignGoalRow).count() == 0:
        db.add(
            SocialCampaignGoalRow(
                title="Build trust for Synapse Network official X",
                objective="Explain the settlement layer for AI agents, prove shipping progress, and attract agent builders/API providers.",
                cadence="daily",
                content_pillars_json=_json_dumps([
                    "Product education",
                    "Shipping proof",
                    "Agent economy commentary",
                    "Developer use cases",
                    "Trust and governance",
                ]),
                success_metrics_json=_json_dumps([
                    "published posts/week",
                    "engagement rate",
                    "profile visits",
                    "staging/docs clicks",
                    "qualified replies",
                ]),
                created_by="system_seed",
            )
        )
    existing_handles = {
        str(row.handle or "").lower()
        for row in db.query(SocialWatchlistAccountRow.handle).all()
    }
    for handle, display_name, category, rationale in DEFAULT_WATCHLIST_ACCOUNTS:
        if handle.lower() not in existing_handles:
            db.add(
                SocialWatchlistAccountRow(
                    handle=handle,
                    display_name=display_name,
                    category=category,
                    rationale=rationale,
                    latest_summary="Not synced yet. Trend radar is read-only until an X read connector is configured.",
                )
            )
            existing_handles.add(handle.lower())
    if db.query(SocialTrendItemRow).count() == 0:
        db.add(
            SocialTrendItemRow(
                topic="AI agents need payment rails",
                summary="Seed trend: agent builders increasingly need budgeted tool/API access. Use as content inspiration, not as sourced claim.",
                relevance_score=0.82,
                status="new",
            )
        )
    try:
        db.commit()
    except IntegrityError:  # pragma: no cover - concurrent startup seed race
        db.rollback()


def list_social_accounts(db: Session) -> list[dict[str, Any]]:
    ensure_default_social_account(db)
    rows = db.query(SocialAccountRow).order_by(SocialAccountRow.platform.asc(), SocialAccountRow.handle.asc()).all()
    return [_account_out(row) for row in rows]


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def start_x_oauth_authorization(db: Session, *, account_id: int | None = None) -> SocialXOAuthStartOut:
    account = _get_account(db, account_id)
    client_id = secret_store.read(config.X_OAUTH_CLIENT_ID_SECRET)
    state = uuid.uuid4().hex
    code_verifier = base64.urlsafe_b64encode(os.urandom(48)).decode("ascii").rstrip("=")
    redirect_uri = config.X_OAUTH_REDIRECT_URI
    expires_at = utcnow() + timedelta(minutes=10)
    session = SocialOAuthSessionRow(
        platform="x",
        account_id=int(account.id),
        state=state,
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
        scope=X_OAUTH_SCOPE,
        status="pending",
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()
    params = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": X_OAUTH_SCOPE,
            "state": state,
            "code_challenge": _pkce_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
    )
    return SocialXOAuthStartOut(auth_url=f"{X_OAUTH_AUTHORIZE_URL}?{params}", state=state, expires_at=expires_at)


def complete_x_oauth_authorization(db: Session, *, state: str, code: str) -> SocialXOAuthCallbackOut:
    clean_state = str(state or "").strip()
    clean_code = str(code or "").strip()
    if not clean_state or not clean_code:
        raise ValueError("OAuth callback requires state and code")
    session = db.query(SocialOAuthSessionRow).filter(SocialOAuthSessionRow.state == clean_state).one_or_none()
    if session is None:
        raise ValueError("OAuth state was not recognized")
    if session.status != "pending":
        raise ValueError("OAuth state was already used")
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < utcnow():
        session.status = "expired"
        db.commit()
        raise ValueError("OAuth state expired; start authorization again")
    account = session.account or ensure_default_social_account(db)
    try:
        x_oauth_token_provider.exchange_authorization_code(
            code=clean_code,
            code_verifier=session.code_verifier,
            redirect_uri=session.redirect_uri,
            profile_ref=account.secret_ref,
        )
    except SocialPublishError as exc:
        session.status = "failed"
        db.commit()
        raise ValueError(exc.summary) from exc
    account.status = "active"
    session.status = "completed"
    session.completed_at = utcnow()
    db.commit()
    return SocialXOAuthCallbackOut(
        status="authorized",
        account_handle=account.handle,
        message=f"@{account.handle} OAuth authorization is ready. Access tokens will be refreshed in memory at publish time.",
    )


def social_ops_overview(db: Session) -> SocialOpsOverviewOut:
    ensure_default_social_account(db)
    ensure_default_social_ops_seed(db)
    return SocialOpsOverviewOut(
        active_goal_count=db.query(SocialCampaignGoalRow).filter(SocialCampaignGoalRow.status == "active").count(),
        draft_queue_count=db.query(SocialPostDraftRow).filter(SocialPostDraftRow.status.in_(["generating", "draft", "needs_review", "approved"])).count(),
        needs_review_count=db.query(SocialPostDraftRow).filter(SocialPostDraftRow.status == "needs_review").count(),
        trend_count=db.query(SocialTrendItemRow).filter(SocialTrendItemRow.status.in_(["new", "saved"])).count(),
        reply_needs_review_count=db.query(SocialReplyItemRow).filter(SocialReplyItemRow.status == "needs_review").count(),
        repost_candidate_count=db.query(SocialRepostCandidateRow).filter(SocialRepostCandidateRow.status == "candidate").count(),
        published_count=db.query(SocialPostDraftRow).filter(SocialPostDraftRow.status == "published").count(),
    )


def _campaign_goal_out(row: SocialCampaignGoalRow) -> SocialCampaignGoalOut:
    return SocialCampaignGoalOut(
        id=int(row.id),
        platform=row.platform,
        title=row.title,
        objective=row.objective,
        status=row.status,
        cadence=row.cadence,
        content_pillars=_json_loads(row.content_pillars_json, []),
        success_metrics=_json_loads(row.success_metrics_json, []),
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_social_campaign_goals(db: Session) -> list[SocialCampaignGoalOut]:
    ensure_default_social_ops_seed(db)
    rows = db.query(SocialCampaignGoalRow).order_by(SocialCampaignGoalRow.status.asc(), SocialCampaignGoalRow.updated_at.desc()).all()
    return [_campaign_goal_out(row) for row in rows]


def create_social_campaign_goal(db: Session, body: SocialCampaignGoalCreateRequest) -> SocialCampaignGoalOut:
    title = str(body.title or "").strip()
    objective = str(body.objective or "").strip()
    if not title or not objective:
        raise ValueError("campaign goal requires title and objective")
    row = SocialCampaignGoalRow(
        title=title,
        objective=objective,
        cadence=str(body.cadence or "daily").strip() or "daily",
        content_pillars_json=_json_dumps(body.content_pillars),
        success_metrics_json=_json_dumps(body.success_metrics),
        created_by=body.created_by or "operator",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _campaign_goal_out(row)


def list_social_trends(db: Session) -> list[SocialTrendItemOut]:
    ensure_default_social_ops_seed(db)
    rows = db.query(SocialTrendItemRow).order_by(SocialTrendItemRow.collected_at.desc(), SocialTrendItemRow.id.desc()).limit(100).all()
    return [_social_trend_out(row) for row in rows]


def _social_trend_source_kind(row: SocialTrendItemRow) -> str:
    if row.source_platform == "x" and str(row.source_url or "").strip():
        return "x_post"
    if not str(row.source_url or "").strip():
        return "local_seed"
    return "other"


def _social_trend_out(row: SocialTrendItemRow) -> SocialTrendItemOut:
    return SocialTrendItemOut(
        id=int(row.id),
        source_platform=row.source_platform,
        source_url=row.source_url,
        author_handle=row.author_handle,
        topic=row.topic,
        summary=row.summary,
        relevance_score=float(row.relevance_score or 0.0),
        status=row.status,
        source_kind=_social_trend_source_kind(row),
        collected_at=row.collected_at,
        updated_at=row.updated_at,
    )


def _parse_operator_local_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"invalid date filter: {value}") from exc


def _operator_local_day_start_utc(value: date) -> datetime:
    zone = _operator_timezone()
    local_start = datetime(value.year, value.month, value.day, tzinfo=zone)
    return local_start.astimezone(timezone.utc)


def _apply_social_trend_source_filter(query, source_kind: str):
    normalized = str(source_kind or "all").strip().lower()
    if normalized == "all":
        return query
    if normalized == "x_post":
        return query.filter(
            SocialTrendItemRow.source_platform == "x",
            SocialTrendItemRow.source_url.isnot(None),
            SocialTrendItemRow.source_url != "",
        )
    if normalized == "local_seed":
        return query.filter(or_(SocialTrendItemRow.source_url.is_(None), SocialTrendItemRow.source_url == ""))
    if normalized == "other":
        return query.filter(
            SocialTrendItemRow.source_platform != "x",
            SocialTrendItemRow.source_url.isnot(None),
            SocialTrendItemRow.source_url != "",
        )
    raise ValueError(f"unsupported source_kind: {source_kind}")


def query_social_trends(
    db: Session,
    *,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    source_kind: str = "all",
    author_handle: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> SocialTrendQueryOut:
    ensure_default_social_ops_seed(db)
    safe_limit = min(max(int(limit or 20), 1), 100)
    safe_offset = max(int(offset or 0), 0)
    query = db.query(SocialTrendItemRow)

    from_day = _parse_operator_local_day(date_from)
    to_day = _parse_operator_local_day(date_to)
    if from_day:
        query = query.filter(SocialTrendItemRow.collected_at >= _operator_local_day_start_utc(from_day))
    if to_day:
        query = query.filter(SocialTrendItemRow.collected_at < _operator_local_day_start_utc(to_day + timedelta(days=1)))

    query = _apply_social_trend_source_filter(query, source_kind)

    normalized_author = str(author_handle or "").strip().lstrip("@")
    if normalized_author:
        query = query.filter(SocialTrendItemRow.author_handle.ilike(normalized_author))

    normalized_q = str(q or "").strip()
    if normalized_q:
        pattern = f"%{normalized_q}%"
        query = query.filter(
            or_(
                SocialTrendItemRow.topic.ilike(pattern),
                SocialTrendItemRow.summary.ilike(pattern),
                SocialTrendItemRow.author_handle.ilike(pattern),
                SocialTrendItemRow.source_url.ilike(pattern),
            )
        )

    total = query.count()
    rows = (
        query.order_by(SocialTrendItemRow.collected_at.desc(), SocialTrendItemRow.id.desc())
        .offset(safe_offset)
        .limit(safe_limit)
        .all()
    )
    return SocialTrendQueryOut(items=[_social_trend_out(row) for row in rows], total=total, limit=safe_limit, offset=safe_offset)


def get_social_trend(db: Session, trend_id: int) -> SocialTrendItemOut:
    ensure_default_social_ops_seed(db)
    row = db.get(SocialTrendItemRow, trend_id)
    if row is None:
        raise ValueError(f"social trend {trend_id} not found")
    return _social_trend_out(row)


def list_social_watchlist(db: Session) -> list[SocialWatchlistAccountOut]:
    ensure_default_social_ops_seed(db)
    rows = db.query(SocialWatchlistAccountRow).order_by(SocialWatchlistAccountRow.category.asc(), SocialWatchlistAccountRow.handle.asc()).all()
    return [
        SocialWatchlistAccountOut(
            id=int(row.id),
            platform=row.platform,
            handle=row.handle,
            display_name=row.display_name,
            category=row.category,
            rationale=row.rationale,
            status=row.status,
            last_checked_at=row.last_checked_at,
            latest_summary=row.latest_summary,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


def list_social_replies(db: Session) -> list[SocialReplyItemOut]:
    rows = db.query(SocialReplyItemRow).order_by(SocialReplyItemRow.updated_at.desc(), SocialReplyItemRow.id.desc()).limit(100).all()
    return [_social_reply_out(row) for row in rows]


def _social_reply_out(row: SocialReplyItemRow) -> SocialReplyItemOut:
    return SocialReplyItemOut(
        id=int(row.id),
        platform=row.platform,
        external_reply_id=row.external_reply_id,
        source_candidate_id=int(row.source_candidate_id) if row.source_candidate_id else None,
        source_post_id=row.source_post_id,
        source_author_handle=row.source_author_handle,
        source_text=row.source_text,
        author_handle=row.author_handle,
        incoming_text=row.incoming_text,
        intent=row.intent,
        suggested_reply=row.suggested_reply,
        generation_reason=row.generation_reason,
        risk_level=row.risk_level,
        status=row.status,
        source_url=row.source_url,
        published_external_post_id=row.published_external_post_id,
        reviewed_by=row.reviewed_by,
        failure_summary=row.failure_summary,
        metadata=_json_loads(row.metadata_json, {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_social_repost_candidates(db: Session) -> list[SocialRepostCandidateOut]:
    rows = db.query(SocialRepostCandidateRow).order_by(SocialRepostCandidateRow.relevance_score.desc(), SocialRepostCandidateRow.updated_at.desc()).limit(100).all()
    return [_repost_candidate_out(row) for row in rows]


def _repost_candidate_out(row: SocialRepostCandidateRow) -> SocialRepostCandidateOut:
    return SocialRepostCandidateOut(
        id=int(row.id),
        platform=row.platform,
        source_url=row.source_url,
        author_handle=row.author_handle,
        source_text=row.source_text,
        suggested_quote=row.suggested_quote,
        relevance_score=float(row.relevance_score or 0.0),
        status=row.status,
        updated_at=row.updated_at,
    )


def _extract_x_post_id(source_url: str | None) -> str:
    text = str(source_url or "").strip()
    if not text:
        return ""
    match = re.search(r"/status(?:es)?/(\d+)", text)
    if match:
        return match.group(1)
    match = re.search(r"(?:tweet_id|post_id|id)=(\d+)", text)
    return match.group(1) if match else ""


def _create_reply_from_repost_candidate(
    db: Session,
    candidate: SocialRepostCandidateRow,
    *,
    actor: str = "x_social_reply_candidate_sweep",
    force_regenerate: bool = False,
) -> SocialReplyItemRow:
    source_url = str(candidate.source_url or "").strip()
    if not source_url:
        raise ValueError("reply candidate requires a real X source URL")
    source_post_id = _extract_x_post_id(source_url)
    if not source_post_id:
        raise ValueError("reply candidate source URL does not include a tweet id")
    existing = (
        db.query(SocialReplyItemRow)
        .filter(
            SocialReplyItemRow.platform == "x",
            or_(
                SocialReplyItemRow.source_candidate_id == int(candidate.id),
                SocialReplyItemRow.source_post_id == source_post_id,
            ),
        )
        .order_by(SocialReplyItemRow.id.desc())
        .first()
    )
    if existing is not None and (
        not force_regenerate or existing.status in {"published", "published_manual", "rejected"}
    ):
        return existing
    row = existing or SocialReplyItemRow(external_reply_id=f"target:{source_post_id}")
    try:
        generated = generate_x_reply_for_candidate(candidate)
        apply_generated_reply_to_row(
            row,
            candidate,
            actor=actor,
            generated=generated,
            failure_summary=None,
            policy=run_content_policy_check(generated.suggested_reply),
        )
    except Exception as exc:
        apply_generated_reply_to_row(
            row,
            candidate,
            actor=actor,
            generated=None,
            failure_summary=reply_agent_failure_summary(exc),
        )
    if existing is None:
        db.add(row)
    db.flush()
    return row


def list_social_post_metrics(db: Session) -> list[SocialPostMetricOut]:
    rows = db.query(SocialPostMetricRow).order_by(SocialPostMetricRow.observed_at.desc(), SocialPostMetricRow.id.desc()).limit(100).all()
    return [
        SocialPostMetricOut(
            id=int(row.id),
            post_id=row.post_id,
            external_post_id=row.external_post_id,
            impressions=int(row.impressions or 0),
            likes=int(row.likes or 0),
            replies=int(row.replies or 0),
            reposts=int(row.reposts or 0),
            follows=int(row.follows or 0),
            link_clicks=int(row.link_clicks or 0),
            summary=row.summary,
            observed_at=row.observed_at,
        )
        for row in rows
    ]


def _daily_planner_raw_metadata(row: SocialPostDraftRow) -> dict[str, Any]:
    data = _json_loads(row.raw_agent_output_json, {})
    if isinstance(data, dict):
        return data
    return {}


def _find_existing_daily_planner_post(
    db: Session,
    *,
    account_id: int,
    local_date: str,
) -> SocialPostDraftRow | None:
    rows = (
        db.query(SocialPostDraftRow)
        .filter(
            SocialPostDraftRow.platform == "x",
            SocialPostDraftRow.account_id == account_id,
            SocialPostDraftRow.source_type == "daily_planner",
        )
        .order_by(SocialPostDraftRow.id.desc())
        .limit(50)
        .all()
    )
    for row in rows:
        raw = _daily_planner_raw_metadata(row)
        if str(raw.get("planner_local_date") or "") == local_date:
            return row
    return None


def _top_social_trends(db: Session, *, limit: int = 3, min_score: float = 0.70) -> list[SocialTrendItemRow]:
    return (
        db.query(SocialTrendItemRow)
        .filter(
            SocialTrendItemRow.status.in_(("new", "saved", "candidate")),
            SocialTrendItemRow.relevance_score >= float(min_score),
        )
        .order_by(SocialTrendItemRow.relevance_score.desc(), SocialTrendItemRow.collected_at.desc(), SocialTrendItemRow.id.desc())
        .limit(max(1, int(limit)))
        .all()
    )


def _watchlist_highlights(db: Session, *, limit: int = 6) -> list[SocialWatchlistAccountRow]:
    priority = ("ai_company", "agent_framework", "agent_protocol", "ai_founder", "ai_researcher", "ai_leader")
    rows = (
        db.query(SocialWatchlistAccountRow)
        .filter(SocialWatchlistAccountRow.status == "active")
        .order_by(SocialWatchlistAccountRow.updated_at.desc(), SocialWatchlistAccountRow.id.asc())
        .all()
    )
    rows.sort(key=lambda row: (priority.index(row.category) if row.category in priority else len(priority), str(row.handle).lower()))
    return rows[: max(1, int(limit))]


X_RELEVANCE_KEYWORDS = (
    "agent",
    "agents",
    "ai agent",
    "mcp",
    "api",
    "apis",
    "payment",
    "payments",
    "micropayment",
    "settlement",
    "infrastructure",
    "infra",
    "developer",
    "developers",
    "tool",
    "tools",
    "automation",
    "autonomous",
)
X_GENERIC_QUOTE_PREFIXES = (
    "great point",
    "well said",
    "interesting",
    "love this",
    "agree",
    "this",
)


def _parse_x_datetime(value: str | None) -> datetime:
    if not value:
        return utcnow()
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return utcnow()
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _x_post_url(handle: str, post_id: str) -> str:
    return f"https://x.com/{str(handle or '').lstrip('@')}/status/{post_id}"


def _x_engagement_score(metrics: dict[str, Any] | None) -> float:
    data = metrics or {}
    likes = int(data.get("like_count") or 0)
    reposts = int(data.get("retweet_count") or data.get("repost_count") or 0)
    replies = int(data.get("reply_count") or 0)
    quotes = int(data.get("quote_count") or 0)
    weighted = likes + (2 * reposts) + replies + (2 * quotes)
    if weighted <= 0:
        return 0.0
    return min(0.30, (weighted ** 0.5) / 50)


def _x_keyword_relevance(text: str) -> float:
    normalized = str(text or "").lower()
    hits = sum(1 for keyword in X_RELEVANCE_KEYWORDS if keyword in normalized)
    return min(0.45, hits * 0.09)


def _x_watchlist_weight(row: SocialWatchlistAccountRow) -> float:
    weights = {
        "agent_founder": 0.18,
        "agent_framework": 0.18,
        "agent_protocol": 0.18,
        "ai_company": 0.14,
        "ai_founder": 0.14,
        "ai_researcher": 0.12,
        "ai_leader": 0.12,
        "ai_operator": 0.12,
    }
    return weights.get(str(row.category or ""), 0.08)


def _score_watchlist_x_post(text: str, metrics: dict[str, Any] | None, watchlist_row: SocialWatchlistAccountRow) -> float:
    base = 0.30
    return min(1.0, base + _x_keyword_relevance(text) + _x_engagement_score(metrics) + _x_watchlist_weight(watchlist_row))


def _x_metrics_summary(metrics: dict[str, Any] | None) -> str:
    data = metrics or {}
    return (
        f"likes={int(data.get('like_count') or 0)}, "
        f"reposts={int(data.get('retweet_count') or data.get('repost_count') or 0)}, "
        f"replies={int(data.get('reply_count') or 0)}, "
        f"quotes={int(data.get('quote_count') or 0)}"
    )


def _is_due_for_x_watchlist_sync(row: SocialWatchlistAccountRow, now: datetime) -> bool:
    if row.last_checked_at is None:
        return True
    checked_at = row.last_checked_at
    if checked_at.tzinfo is not None:
        checked_at = checked_at.astimezone(timezone.utc).replace(tzinfo=None)
    comparison_now = now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo is not None else now
    return checked_at <= comparison_now - timedelta(minutes=config.X_WATCHLIST_SYNC_INTERVAL_MINUTES)


def _should_keep_x_post(post: XPost, score: float, *, min_relevance_score: float) -> bool:
    if len(str(post.text or "").strip()) < config.X_TREND_MIN_TEXT_CHARS:
        return False
    return score >= float(min_relevance_score)


def _is_value_add_quote(quote: str | None, source_text: str) -> bool:
    text = str(quote or "").strip()
    if len(text) < 80:
        return False
    lowered = text.lower()
    if any(lowered.startswith(prefix) for prefix in X_GENERIC_QUOTE_PREFIXES):
        return False
    source_normalized = _normalize_for_copy_check(source_text)
    quote_normalized = _normalize_for_copy_check(text)
    if source_normalized and quote_normalized and (quote_normalized in source_normalized or source_normalized in quote_normalized):
        return False
    return "synapse" in lowered or "agent" in lowered or "api" in lowered or "payment" in lowered


def _sync_x_watchlist_timeline_posts(db: Session, *, min_relevance_score: float) -> dict[str, Any]:
    now = utcnow()
    due_accounts = (
        db.query(SocialWatchlistAccountRow)
        .filter(SocialWatchlistAccountRow.platform == "x", SocialWatchlistAccountRow.status == "active")
        .order_by(SocialWatchlistAccountRow.last_checked_at.asc().nullsfirst(), SocialWatchlistAccountRow.id.asc())
        .all()
    )
    due_accounts = [row for row in due_accounts if _is_due_for_x_watchlist_sync(row, now)][: config.X_WATCHLIST_MAX_ACCOUNTS_PER_SWEEP]
    if not due_accounts:
        return {
            "connector": "x_watchlist_timeline",
            "x_read_connector_configured": True,
            "due_watchlist_count": 0,
            "created_trend_ids": [],
            "skipped_short_text_count": 0,
            "skipped_low_relevance_count": 0,
            "duplicate_count": 0,
            "rate_limited": False,
            "diagnostic": "No watchlist accounts are due for X timeline sync.",
        }

    token_result = x_oauth_token_provider.get_access_token(DEFAULT_X_SECRET_REF)
    client = XApiClient(token_result.access_token)
    created_ids: list[int] = []
    skipped_short = 0
    skipped_low = 0
    duplicate_count = 0
    synced_handles: list[str] = []
    diagnostic = "Synced due watchlist accounts from X user timelines."

    for account in due_accounts:
        handle = str(account.handle or "").strip().lstrip("@")
        try:
            user = client.get_user_by_username(handle)
            posts = client.get_user_tweets(user.id, max_results=config.X_WATCHLIST_TWEETS_PER_ACCOUNT)
        except XApiRateLimitError as exc:
            account.last_checked_at = now
            account.latest_summary = "X API rate limit reached; this account will be retried after the watchlist sync interval."
            diagnostic = f"X API rate limit reached while syncing @{handle}: {_bounded_excerpt(str(exc), max_chars=300)}"
            db.commit()
            return {
                "connector": "x_watchlist_timeline",
                "x_read_connector_configured": True,
                "due_watchlist_count": len(due_accounts),
                "synced_handles": synced_handles,
                "created_trend_ids": created_ids,
                "skipped_short_text_count": skipped_short,
                "skipped_low_relevance_count": skipped_low,
                "duplicate_count": duplicate_count,
                "rate_limited": True,
                "diagnostic": diagnostic,
            }
        except (XApiAuthError, XApiTransientError) as exc:
            account.last_checked_at = now
            account.latest_summary = f"X timeline sync failed: {_bounded_excerpt(str(exc), max_chars=240)}"
            diagnostic = f"X timeline sync failed for @{handle}: {_bounded_excerpt(str(exc), max_chars=300)}"
            continue

        synced_handles.append(handle)
        account.last_checked_at = now
        account.display_name = account.display_name or user.name
        if not posts:
            account.latest_summary = "X timeline returned no recent public posts."
            continue
        account.latest_summary = _bounded_excerpt(posts[0].text, max_chars=240)
        for post in posts:
            source_url = _x_post_url(user.username, post.id)
            if db.query(SocialTrendItemRow.id).filter(SocialTrendItemRow.source_url == source_url).first():
                duplicate_count += 1
                continue
            score = _score_watchlist_x_post(post.text, post.public_metrics, account)
            if len(str(post.text or "").strip()) < config.X_TREND_MIN_TEXT_CHARS:
                skipped_short += 1
                continue
            if not _should_keep_x_post(post, score, min_relevance_score=min_relevance_score):
                skipped_low += 1
                continue
            topic = _bounded_excerpt(str(post.text or "").splitlines()[0], max_chars=96)
            summary = _bounded_excerpt(
                f"{post.text}\n\nSource: X watchlist @{user.username}. Public metrics: {_x_metrics_summary(post.public_metrics)}.",
                max_chars=1000,
            )
            row = SocialTrendItemRow(
                source_platform="x",
                source_url=source_url,
                author_handle=user.username,
                topic=topic or f"@{user.username} watchlist update",
                summary=summary,
                relevance_score=score,
                status="new",
                collected_at=_parse_x_datetime(post.created_at),
            )
            db.add(row)
            db.flush()
            created_ids.append(int(row.id))
    db.commit()
    return {
        "connector": "x_watchlist_timeline",
        "x_read_connector_configured": True,
        "due_watchlist_count": len(due_accounts),
        "synced_handles": synced_handles,
        "created_trend_ids": created_ids,
        "skipped_short_text_count": skipped_short,
        "skipped_low_relevance_count": skipped_low,
        "duplicate_count": duplicate_count,
        "rate_limited": False,
        "diagnostic": diagnostic,
    }


def _recent_social_metric_rows(db: Session, *, limit: int = 3) -> list[SocialPostMetricRow]:
    return (
        db.query(SocialPostMetricRow)
        .order_by(SocialPostMetricRow.observed_at.desc(), SocialPostMetricRow.id.desc())
        .limit(max(1, int(limit)))
        .all()
    )


def _build_daily_planner_prompt(
    db: Session,
    *,
    local_date: str,
) -> tuple[str, dict[str, Any]]:
    goal = (
        db.query(SocialCampaignGoalRow)
        .filter(SocialCampaignGoalRow.platform == "x", SocialCampaignGoalRow.status == "active")
        .order_by(SocialCampaignGoalRow.updated_at.desc(), SocialCampaignGoalRow.id.desc())
        .first()
    )
    trends = _top_social_trends(db)
    watchlist = _watchlist_highlights(db)
    metrics = _recent_social_metric_rows(db)
    variable_candidates: list[str] = []
    variable_candidates.extend([f"Trend: {trend.topic} — {trend.summary}" for trend in trends])
    variable_candidates.extend([f"Watchlist: @{row.handle} — {row.rationale or row.latest_summary or row.display_name or row.handle}" for row in watchlist])
    variable_factor = variable_candidates[0] if variable_candidates else "Fresh angle: explain why autonomous agents need governed API access and payment rails."
    if variable_candidates:
        day_offset = sum(int(part) for part in local_date.split("-") if part.isdigit())
        variable_factor = variable_candidates[day_offset % len(variable_candidates)]

    content_pillars = _json_loads(goal.content_pillars_json, []) if goal else []
    success_metrics = _json_loads(goal.success_metrics_json, []) if goal else []
    metric_lines = [
        f"- post_metric_id={row.id}: impressions={row.impressions}, likes={row.likes}, replies={row.replies}, reposts={row.reposts}, link_clicks={row.link_clicks}, summary={row.summary or 'no summary'}"
        for row in metrics
    ]
    prompt = "\n".join(
        [
            f"Create today's human-reviewed X official account draft for Synapse Network. Local date: {local_date}.",
            "This is a scheduled daily planner draft. Do not publish, reply, repost, follow, delete, or claim an external action happened.",
            "",
            "# Active campaign goal",
            f"Title: {goal.title if goal else 'Build trust for Synapse Network official X'}",
            f"Objective: {goal.objective if goal else 'Explain Synapse Network to AI agent builders and API providers.'}",
            f"Content pillars: {', '.join(str(item) for item in content_pillars) or 'Product education, shipping proof, agent economy commentary, developer use cases, trust and governance'}",
            f"Success metrics: {', '.join(str(item) for item in success_metrics) or 'published posts/week, engagement rate, profile visits, docs clicks'}",
            "",
            "# Variable factor for freshness",
            variable_factor,
            "",
            "# Top trend radar items",
            "\n".join(f"- {trend.topic}: {trend.summary} (score={trend.relevance_score:.2f})" for trend in trends) or "- metrics_unavailable: no high-quality trend radar item yet.",
            "",
            "# Watchlist highlights",
            "\n".join(f"- @{row.handle} ({row.category}): {row.rationale or row.latest_summary or row.display_name or row.handle}" for row in watchlist) or "- no watchlist highlights available.",
            "",
            "# Recent 3 published post performance",
            "\n".join(metric_lines) or "- metrics_unavailable: no recent post metrics yet.",
            "",
            "Write a substantial, high-trust X post with a strong hook, concrete product value, and relevant hashtags. Keep it public-facing and useful to AI agent builders, API providers, and developer operators.",
        ]
    )
    metadata = {
        "planner_local_date": local_date,
        "trend_item_ids": [int(row.id) for row in trends],
        "watchlist_handles": [str(row.handle) for row in watchlist],
        "recent_metric_post_ids": [int(row.post_id) for row in metrics if row.post_id is not None],
        "variable_factor": variable_factor,
        "metrics_available": bool(metrics),
    }
    return prompt, metadata


def run_x_social_daily_content_planner(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """Generate at most one human-reviewed X draft per operator-local day."""

    ensure_default_social_ops_seed(db)
    account = ensure_default_social_account(db)
    local_date = _operator_local_date(now)
    planner_run_key = f"x_daily:{int(account.id)}:{local_date}"
    existing = _find_existing_daily_planner_post(db, account_id=int(account.id), local_date=local_date)
    if existing is not None:
        return {
            "already_created": True,
            "created_post_id": None,
            "existing_post_id": int(existing.id),
            "planner_local_date": local_date,
            "planner_run_key": planner_run_key,
            "status": existing.status,
        }

    prompt, metadata = _build_daily_planner_prompt(db, local_date=local_date)
    metadata = {**metadata, "planner_run_key": planner_run_key, "source_type": "daily_planner"}
    row = SocialPostDraftRow(
        platform="x",
        account_id=int(account.id),
        source_type="daily_planner",
        title="X daily planner draft is generating",
        body_text="",
        status="generating",
        generated_by="x_social_daily_content_planner",
        policy_check_json=_json_dumps(_generation_running_policy()),
        raw_agent_output_json=_json_dumps(
            {
                "source": "x_social_daily_content_planner",
                "status": "generating",
                "provider": config.SOCIAL_CONTENT_LLM_PROVIDER,
                "requested_model": config.SOCIAL_CONTENT_LLM_MODEL,
                "media_mode": "text_only",
                "prompt_excerpt": _bounded_excerpt(prompt, max_chars=240),
                **metadata,
            }
        ),
    )
    db.add(row)
    db.flush()
    _record_event(
        db,
        row,
        "daily_planner_generation_started",
        actor="x_social_daily_content_planner",
        summary="Hourly X social planner created today's draft shell; no external publish attempted.",
        payload={"planner_local_date": local_date, "planner_run_key": planner_run_key},
    )
    db.commit()
    _finalize_generated_social_post(
        db,
        int(row.id),
        prompt=prompt,
        actor="x_social_daily_content_planner",
        style_type="marketing",
        media_mode="text_only",
    )
    row = _get_post(db, int(row.id))
    raw = _daily_planner_raw_metadata(row)
    raw.update(metadata)
    raw["source"] = "x_social_daily_content_planner"
    row.raw_agent_output_json = _json_dumps(raw)
    if row.status == "approved":
        row.status = "needs_review"
        row.reviewed_by = None
        _record_event(
            db,
            row,
            "daily_planner_requires_human_review",
            actor="x_social_daily_content_planner",
            summary="Policy passed, but scheduled X drafts remain in needs_review until an operator approves publishing.",
            payload={"planner_local_date": local_date, "planner_run_key": planner_run_key},
        )
    db.commit()
    return {
        "already_created": False,
        "created_post_id": int(row.id),
        "existing_post_id": None,
        "planner_local_date": local_date,
        "planner_run_key": planner_run_key,
        "status": row.status,
        "policy_status": _json_loads(row.policy_check_json, {}).get("status"),
        "trend_item_ids": metadata["trend_item_ids"],
        "watchlist_handles": metadata["watchlist_handles"],
        "recent_metric_post_ids": metadata["recent_metric_post_ids"],
    }


def run_x_social_trend_radar_sweep(db: Session, *, min_relevance_score: float = 0.70) -> dict[str, Any]:
    """Read X watchlist timelines, then summarize retained trend items.

    The sweep is read-only against X: it never likes, follows, replies, reposts,
    or publishes. If X auth/rate limits are unavailable, it records diagnostics
    and falls back to filtering existing rows without inventing sourced trends.
    """

    ensure_default_social_ops_seed(db)
    watchlist_sync: dict[str, Any]
    try:
        watchlist_sync = _sync_x_watchlist_timeline_posts(db, min_relevance_score=min_relevance_score)
    except SocialPublishError as exc:
        watchlist_sync = {
            "connector": "local_seed_and_existing_trends",
            "x_read_connector_configured": False,
            "created_trend_ids": [],
            "rate_limited": False,
            "diagnostic": f"X watchlist timeline sync unavailable: {exc.summary}",
        }
    candidates = (
        db.query(SocialTrendItemRow)
        .filter(SocialTrendItemRow.status.in_(("new", "saved", "candidate")))
        .order_by(SocialTrendItemRow.relevance_score.desc(), SocialTrendItemRow.collected_at.desc(), SocialTrendItemRow.id.desc())
        .limit(100)
        .all()
    )
    retained = [row for row in candidates if float(row.relevance_score or 0.0) >= float(min_relevance_score)]
    filtered = [row for row in candidates if row not in retained]
    watchlist_count = db.query(SocialWatchlistAccountRow).filter(SocialWatchlistAccountRow.status == "active").count()
    return {
        "read_only": True,
        "external_actions": [],
        "connector": watchlist_sync.get("connector", "local_seed_and_existing_trends"),
        "x_read_connector_configured": bool(watchlist_sync.get("x_read_connector_configured")),
        "min_relevance_score": float(min_relevance_score),
        "retained_count": len(retained),
        "filtered_count": len(filtered),
        "retained_trend_ids": [int(row.id) for row in retained],
        "watchlist_active_count": int(watchlist_count),
        "created_trend_ids": watchlist_sync.get("created_trend_ids", []),
        "due_watchlist_count": int(watchlist_sync.get("due_watchlist_count") or 0),
        "synced_handles": watchlist_sync.get("synced_handles", []),
        "skipped_short_text_count": int(watchlist_sync.get("skipped_short_text_count") or 0),
        "skipped_low_relevance_count": int(watchlist_sync.get("skipped_low_relevance_count") or 0),
        "duplicate_count": int(watchlist_sync.get("duplicate_count") or 0),
        "rate_limited": bool(watchlist_sync.get("rate_limited")),
        "diagnostic": watchlist_sync.get("diagnostic")
        or "Sweep filtered existing trend rows and watchlist timeline inputs only.",
    }


def run_x_social_repost_candidate_sweep(db: Session, *, min_relevance_score: float = 0.75, max_created: int = 5) -> dict[str, Any]:
    """Create human-gated quote/repost candidates from retained trend items only."""

    ensure_default_social_ops_seed(db)
    trends = _top_social_trends(db, limit=25, min_score=min_relevance_score)
    created_ids: list[int] = []
    skipped_ids: list[int] = []
    existing_texts = {
        _normalize_for_copy_check(str(row[0] or ""))
        for row in db.query(SocialRepostCandidateRow.source_text).all()
    }
    for trend in trends:
        if len(created_ids) >= max(1, int(max_created)):
            break
        if not trend.source_url:
            skipped_ids.append(int(trend.id))
            continue
        source_text = f"{trend.topic}: {trend.summary}".strip()
        normalized = _normalize_for_copy_check(source_text)
        if normalized in existing_texts:
            skipped_ids.append(int(trend.id))
            continue
        quote = (
            "Relevant signal for AI agent builders: "
            f"{trend.summary} Synapse angle: autonomous agents need governed API access, budgets, and payment rails."
        )
        if not _is_value_add_quote(quote, source_text):
            skipped_ids.append(int(trend.id))
            continue
        row = SocialRepostCandidateRow(
            platform="x",
            source_url=trend.source_url,
            author_handle=trend.author_handle,
            source_text=source_text,
            suggested_quote=_bounded_excerpt(quote, max_chars=1000),
            relevance_score=float(trend.relevance_score or 0.0),
            status="candidate",
        )
        db.add(row)
        db.flush()
        created_ids.append(int(row.id))
        existing_texts.add(normalized)
    db.commit()
    return {
        "read_only": True,
        "external_actions": [],
        "created_candidate_ids": created_ids,
        "skipped_trend_ids": skipped_ids,
        "source_trend_ids": [int(row.id) for row in trends],
        "min_relevance_score": float(min_relevance_score),
        "human_gate_required": True,
    }


def run_x_social_reply_candidate_sweep(db: Session, *, max_created: int = 1) -> dict[str, Any]:
    """Create human-reviewed reply drafts from real X repost candidates.

    The sweep never calls X write APIs. It chooses at most one unprocessed
    candidate per run so a 30-minute cadence cannot turn into reply spam.
    """

    ensure_default_social_ops_seed(db)
    existing_candidate_ids = {
        int(row[0])
        for row in db.query(SocialReplyItemRow.source_candidate_id)
        .filter(SocialReplyItemRow.source_candidate_id.isnot(None))
        .all()
        if row[0] is not None
    }
    candidates = (
        db.query(SocialRepostCandidateRow)
        .filter(
            SocialRepostCandidateRow.status == "candidate",
            SocialRepostCandidateRow.source_url.isnot(None),
        )
        .order_by(SocialRepostCandidateRow.relevance_score.desc(), SocialRepostCandidateRow.updated_at.desc(), SocialRepostCandidateRow.id.desc())
        .limit(25)
        .all()
    )
    created_ids: list[int] = []
    skipped_ids: list[int] = []
    for candidate in candidates:
        if len(created_ids) >= max(1, int(max_created)):
            break
        if int(candidate.id) in existing_candidate_ids:
            skipped_ids.append(int(candidate.id))
            continue
        if not _extract_x_post_id(candidate.source_url):
            skipped_ids.append(int(candidate.id))
            continue
        try:
            row = _create_reply_from_repost_candidate(db, candidate, actor="x_social_reply_candidate_sweep")
        except ValueError:
            skipped_ids.append(int(candidate.id))
            continue
        created_ids.append(int(row.id))
        existing_candidate_ids.add(int(candidate.id))
    db.commit()
    return {
        "read_only": False,
        "auto_publish": False,
        "external_actions": [],
        "human_gate_required": True,
        "created_reply_ids": created_ids,
        "skipped_candidate_ids": skipped_ids,
        "candidate_count": len(candidates),
        "no_candidate": not bool(created_ids),
    }


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


def get_social_post(db: Session, post_id: int) -> SocialPostDraftOut:
    """Return one social draft with its process timeline and publish result."""

    return _post_out(_get_post(db, post_id))


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
        source_type=body.source_type or "manual_prompt",
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


def _generate_media_asset_for_post(
    db: Session,
    row: SocialPostDraftRow,
    *,
    prompt: str,
    alt_text: str | None,
    actor: str,
) -> None:
    _validate_image_prompt(prompt, alt_text)
    media = SocialPostMediaAssetRow(
        post_id=int(row.id),
        media_type="image",
        status="generating",
        prompt=prompt,
        alt_text=alt_text,
    )
    db.add(media)
    db.flush()
    try:
        result = image_generator.generate_image(prompt=prompt, asset_id=int(media.id))
        media.status = "ready"
        media.local_path = result.local_path
        media.preview_url = result.preview_url
        media.failure_summary = None
        _record_event(
            db,
            row,
            "image_generated",
            actor=actor,
            summary="Agent generated a reviewable X image asset.",
            payload={"media_asset_id": int(media.id), "provider": config.SOCIAL_IMAGE_PROVIDER, "model": config.SOCIAL_IMAGE_MODEL},
        )
    except Exception as exc:
        media.status = "failed"
        media.failure_summary = _bounded_excerpt(str(exc), max_chars=1000)
        _record_event(
            db,
            row,
            "image_generation_failed",
            actor=actor,
            summary=media.failure_summary,
            payload={"media_asset_id": int(media.id), "provider": config.SOCIAL_IMAGE_PROVIDER, "model": config.SOCIAL_IMAGE_MODEL},
        )


def _finalize_generated_social_post(
    db: Session,
    post_id: int,
    *,
    prompt: str,
    actor: str,
    style_type: str | None = None,
    media_mode: str | None = None,
) -> None:
    row = db.get(SocialPostDraftRow, post_id)
    if row is None:
        logger.warning("social_generation_post_missing", extra={"post_id": post_id})
        return
    if row.status != "generating":
        logger.info("social_generation_skipped_non_generating", extra={"post_id": post_id, "status": row.status})
        return
    normalized_media_mode = _normalize_media_mode(media_mode)
    db.rollback()
    try:
        generated = _generate_x_post_copy(prompt, style_type=style_type, media_mode=normalized_media_mode)
        policy = run_content_policy_check(generated.body_text)
        row = db.get(SocialPostDraftRow, post_id)
        if row is None:  # pragma: no cover - stale async job race
            logger.warning("social_generation_post_missing_after_generation", extra={"post_id": post_id})
            return
        if row.status != "generating":  # pragma: no cover - operator changed draft mid-generation
            logger.info("social_generation_skipped_after_generation", extra={"post_id": post_id, "status": row.status})
            return
        generated_status = "approved" if policy["status"] == "passed" else "needs_review"
        row.title = generated.title
        row.body_text = generated.body_text
        row.status = generated_status
        row.reviewed_by = actor if generated_status == "approved" else None
        row.failure_summary = None
        row.policy_check_json = _json_dumps(policy)
        row.raw_agent_output_json = _json_dumps(
            {
                "source": "llm_social_content_agent_v1",
                "provider": config.SOCIAL_CONTENT_LLM_PROVIDER,
                "requested_model": config.SOCIAL_CONTENT_LLM_MODEL,
                "model": generated.model or config.SOCIAL_CONTENT_LLM_MODEL,
                "context_sources": list(generated.context_sources),
                "media_support": "single_image_v1",
                "media_mode": normalized_media_mode,
                "media_decision": generated.media_decision,
                "image_prompt": generated.image_prompt,
                "image_alt_text": generated.image_alt_text,
                "prompt_excerpt": _bounded_excerpt(prompt, max_chars=240),
                "style_type": (generated.generation_metadata or {}).get("style_type", _normalize_style_type(style_type)),
                "generation_metadata": generated.generation_metadata or {},
            }
        )
        if generated.media_decision == "image":
            _generate_media_asset_for_post(
                db,
                row,
                prompt=str(generated.image_prompt or ""),
                alt_text=generated.image_alt_text,
                actor=actor,
            )
        _record_event(
            db,
            row,
            "agent_draft_generated",
            actor=actor,
            summary="Agent generated an X draft from operator prompt; no external publish attempted.",
            payload={
                "policy_status": policy["status"],
                "generated_status": generated_status,
                "media_decision": generated.media_decision,
                "prompt_excerpt": _bounded_excerpt(prompt, max_chars=240),
                "style_type": (generated.generation_metadata or {}).get("style_type", _normalize_style_type(style_type)),
            },
        )
    except Exception as exc:
        row = db.get(SocialPostDraftRow, post_id)
        if row is None:  # pragma: no cover - stale async job race
            logger.warning("social_generation_failure_post_missing", extra={"post_id": post_id})
            return
        row.status = "failed"
        row.failure_summary = _bounded_excerpt(str(exc), max_chars=1000)
        row.policy_check_json = _json_dumps(run_content_policy_check(row.body_text or ""))
        row.raw_agent_output_json = _json_dumps(
            {
                "source": "llm_social_content_agent_v1",
                "provider": config.SOCIAL_CONTENT_LLM_PROVIDER,
                "requested_model": config.SOCIAL_CONTENT_LLM_MODEL,
                "media_support": "single_image_v1",
                "media_mode": normalized_media_mode,
                "prompt_excerpt": _bounded_excerpt(prompt, max_chars=240),
                "style_type": _normalize_style_type(style_type),
                "error": row.failure_summary,
            }
        )
        _record_event(
            db,
            row,
            "agent_generation_failed",
            actor=actor,
            summary=row.failure_summary,
            payload={"prompt_excerpt": _bounded_excerpt(prompt, max_chars=240), "style_type": _normalize_style_type(style_type), "media_mode": normalized_media_mode},
        )
    finally:
        db.commit()


def _run_generated_social_post_job(
    post_id: int,
    *,
    prompt: str,
    actor: str,
    style_type: str | None = None,
    media_mode: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        _finalize_generated_social_post(db, post_id, prompt=prompt, actor=actor, style_type=style_type, media_mode=media_mode)
    finally:
        db.close()


def generate_social_post_draft(db: Session, body: SocialPostGenerateDraftRequest, *, background_tasks: Any | None = None) -> SocialPostDraftOut:
    """Queue an X draft generation job and return a visible generating row immediately."""

    prompt = str(body.prompt or "").strip()
    if not prompt:
        raise ValueError("prompt is required for Agent draft generation")
    style_type = _normalize_style_type(body.style_type)
    media_mode = _normalize_media_mode(body.media_mode)
    account = _get_account(db, body.account_id)
    actor = body.actor or "operator"
    row = SocialPostDraftRow(
        platform="x",
        account_id=int(account.id),
        source_type="manual_prompt",
        title="Agent 正在生成草稿",
        body_text="",
        status="generating",
        generated_by="social_content_agent_v1",
        reviewed_by=None,
        target_audience=None,
        cta=None,
        agent_rationale=None,
        policy_check_json=_json_dumps(_generation_running_policy()),
        raw_agent_output_json=_json_dumps(
            {
                "source": "llm_social_content_agent_v1",
                "provider": config.SOCIAL_CONTENT_LLM_PROVIDER,
                "requested_model": config.SOCIAL_CONTENT_LLM_MODEL,
                "media_support": "single_image_v1",
                "media_mode": media_mode,
                "status": "generating",
                "prompt_excerpt": _bounded_excerpt(prompt, max_chars=240),
                "style_type": style_type,
            }
        ),
    )
    db.add(row)
    db.flush()
    _record_event(
        db,
        row,
        "agent_generation_started",
        actor=actor,
        summary="Agent draft generation started; no external publish attempted.",
        payload={
            "prompt_excerpt": _bounded_excerpt(prompt, max_chars=240),
            "style_type": style_type,
            "media_mode": media_mode,
        },
    )
    db.commit()
    db.refresh(row)
    if background_tasks is not None:
        background_tasks.add_task(_run_generated_social_post_job, int(row.id), prompt=prompt, actor=actor, style_type=style_type, media_mode=media_mode)
    else:
        _run_generated_social_post_job(int(row.id), prompt=prompt, actor=actor, style_type=style_type, media_mode=media_mode)
    return _post_out(row)


def update_social_post(db: Session, post_id: int, body: SocialPostPatchRequest) -> SocialPostDraftOut:
    row = _get_post(db, post_id)
    if row.status == "generating":
        raise ValueError("social post draft is still generating")
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


def get_social_media_preview_path(db: Session, media_id: int) -> Path:
    row = db.get(SocialPostMediaAssetRow, media_id)
    if row is None or row.status not in {"ready", "uploaded"} or not row.local_path:
        raise ValueError("social media preview not found")
    path = Path(row.local_path)
    runtime_root = _media_runtime_dir().resolve()
    resolved = path.resolve()
    if runtime_root not in resolved.parents and resolved != runtime_root:
        raise ValueError("social media preview path is outside the managed runtime directory")
    if not resolved.is_file():
        raise ValueError("social media preview file is missing")
    return resolved


def regenerate_social_post_image(db: Session, post_id: int, *, actor: str = "operator") -> SocialPostDraftOut:
    row = _get_post(db, post_id)
    if row.status in HUMAN_SETTLED_STATUSES or row.status == "publishing":
        raise ValueError("settled social posts cannot regenerate images")
    existing_assets = sorted(getattr(row, "media_assets", []) or [], key=lambda asset: int(asset.id or 0))
    active_assets = [asset for asset in existing_assets if asset.media_type == "image" and asset.status != "removed"]
    raw_output = _json_loads(row.raw_agent_output_json, {})
    prompt = str((active_assets[-1].prompt if active_assets else None) or raw_output.get("image_prompt") or "").strip()
    alt_text = str((active_assets[-1].alt_text if active_assets else None) or raw_output.get("image_alt_text") or "").strip()
    if not prompt:
        prompt, alt_text = _fallback_image_prompt_for_post(row)
        raw_output["image_prompt"] = prompt
        raw_output["image_alt_text"] = alt_text
        raw_output["image_prompt_source"] = "deterministic_content_fallback"
        row.raw_agent_output_json = _json_dumps(raw_output)
    for asset in active_assets:
        asset.status = "removed"
    _generate_media_asset_for_post(db, row, prompt=prompt, alt_text=alt_text, actor=actor)
    _record_event(db, row, "image_regenerated", actor=actor, summary="Operator regenerated the X image asset.")
    db.commit()
    db.refresh(row)
    return _post_out(row)


def remove_social_post_media(db: Session, post_id: int, media_id: int, *, actor: str = "operator") -> SocialPostDraftOut:
    row = _get_post(db, post_id)
    if row.status in HUMAN_SETTLED_STATUSES or row.status == "publishing":
        raise ValueError("settled social posts cannot remove media")
    media = db.get(SocialPostMediaAssetRow, media_id)
    if media is None or int(media.post_id) != int(row.id):
        raise ValueError("social media asset not found")
    media.status = "removed"
    media.failure_summary = None
    _record_event(
        db,
        row,
        "image_removed",
        actor=actor,
        summary=f"Operator removed image media asset {media_id} from the X draft.",
        payload={"media_asset_id": media_id},
    )
    db.commit()
    db.refresh(row)
    return _post_out(row)


def upload_social_post_image(
    db: Session,
    post_id: int,
    *,
    filename: str | None,
    content_type: str | None,
    payload: bytes,
    alt_text: str | None = None,
    actor: str = "operator",
) -> SocialPostDraftOut:
    row = _get_post(db, post_id)
    if row.status in HUMAN_SETTLED_STATUSES or row.status == "publishing":
        raise ValueError("settled social posts cannot upload media")
    extension = _validate_uploaded_image(filename, content_type, payload)
    existing_assets = sorted(getattr(row, "media_assets", []) or [], key=lambda asset: int(asset.id or 0))
    for asset in existing_assets:
        if asset.media_type == "image" and asset.status != "removed":
            asset.status = "removed"
            asset.failure_summary = None
    media = SocialPostMediaAssetRow(
        post_id=int(row.id),
        media_type="image",
        status="ready",
        prompt="manual_upload",
        alt_text=str(alt_text or "Operator uploaded image for X post").strip()[:500],
    )
    db.add(media)
    db.flush()
    output_path = _media_runtime_dir() / f"social-post-media-{int(media.id)}-manual{extension}"
    output_path.write_bytes(payload)
    media.local_path = str(output_path)
    media.preview_url = _media_preview_url(int(media.id))
    media.failure_summary = None
    _record_event(
        db,
        row,
        "image_uploaded_manual",
        actor=actor,
        summary="Operator uploaded a reviewable X image asset.",
        payload={
            "media_asset_id": int(media.id),
            "filename": filename or "",
            "content_type": content_type or "",
            "size_bytes": len(payload),
        },
    )
    db.commit()
    db.refresh(row)
    return _post_out(row)


@dataclass
class XOAuth2AccessToken:
    access_token: str
    refreshed: bool = False
    refresh_token_rotated: bool = False


class SecretValueStore:
    """Read/write secret values without exposing them to API payloads or logs."""

    def _secret_name(self, secret_ref: str) -> str:
        ref = str(secret_ref or "").strip()
        if not ref:
            raise SocialPublishError("x_auth_failed", "X credential secret reference is empty.")
        if ref.startswith("projects/"):
            return ref
        project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("STAGING_GCP_PROJECT_ID")
        if not project_id:
            raise SocialPublishError("x_auth_failed", "GCP project id is required to read the X credential secret.")
        return f"projects/{project_id}/secrets/{ref}/versions/latest"

    def _secret_parent(self, secret_ref: str) -> str:
        ref = str(secret_ref or "").strip()
        if not ref:
            raise SocialPublishError("x_auth_failed", "X credential secret reference is empty.")
        if ref.startswith("projects/"):
            return ref.rsplit("/versions/", 1)[0]
        project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("STAGING_GCP_PROJECT_ID")
        if not project_id:
            raise SocialPublishError("x_auth_failed", "GCP project id is required to write the X credential secret.")
        return f"projects/{project_id}/secrets/{ref}"

    def _secret_create_request(self, secret_ref: str) -> dict[str, Any]:
        parent = self._secret_parent(secret_ref)
        if "/secrets/" not in parent:
            raise SocialPublishError("x_refresh_failed", "X refresh token secret reference is invalid.")
        project_parent, secret_id = parent.rsplit("/secrets/", 1)
        if not project_parent or not secret_id:
            raise SocialPublishError("x_refresh_failed", "X refresh token secret reference is invalid.")
        return {
            "parent": project_parent,
            "secret_id": secret_id,
            "secret": {"replication": {"automatic": {}}},
        }

    def _is_secret_not_found(self, exc: Exception) -> bool:
        try:
            from google.api_core import exceptions as google_exceptions  # type: ignore

            if isinstance(exc, google_exceptions.NotFound):
                return True
        except Exception:  # pragma: no cover - optional dependency shape
            pass
        return "not found" in str(exc).lower()

    def read(self, secret_ref: str) -> str:
        ref = str(secret_ref or "").strip()
        if ref.startswith("env:"):
            value = os.environ.get(ref.removeprefix("env:"), "")
            if not value:
                raise SocialPublishError("x_auth_failed", "X credential environment variable is missing.")
            return value
        try:
            from google.cloud import secretmanager  # type: ignore
        except Exception as exc:  # pragma: no cover - optional production dependency
            raise SocialPublishError("x_auth_failed", "Google Secret Manager client is unavailable in this runtime.") from exc
        try:
            response = secretmanager.SecretManagerServiceClient().access_secret_version(request={"name": self._secret_name(ref)})
        except Exception as exc:  # pragma: no cover - credential dependent
            if _is_gcp_adc_reauth_error(exc):
                raise SocialPublishError("gcp_adc_expired", _gcp_adc_reauth_summary()) from exc
            raise SocialPublishError("x_auth_failed", f"Secret Manager read failed: {_bounded_excerpt(str(exc))}") from exc
        value = response.payload.data.decode("utf-8", errors="replace").strip()
        if not value:
            raise SocialPublishError("x_auth_failed", "X credential secret is empty.")
        return value

    def add_version(self, secret_ref: str, value: str) -> None:
        ref = str(secret_ref or "").strip()
        if ref.startswith("env:"):
            raise SocialPublishError("x_refresh_failed", "X refresh token cannot be rotated into an environment variable.")
        try:
            from google.cloud import secretmanager  # type: ignore
        except Exception as exc:  # pragma: no cover - optional production dependency
            raise SocialPublishError("x_refresh_failed", "Google Secret Manager client is unavailable in this runtime.") from exc
        client = secretmanager.SecretManagerServiceClient()
        request = {
            "parent": self._secret_parent(ref),
            "payload": {"data": value.encode("utf-8")},
        }
        try:
            client.add_secret_version(
                request={
                    "parent": request["parent"],
                    "payload": request["payload"],
                }
            )
        except Exception as exc:  # pragma: no cover - credential dependent
            if _is_gcp_adc_reauth_error(exc):
                raise SocialPublishError("gcp_adc_expired", _gcp_adc_reauth_summary()) from exc
            if not self._is_secret_not_found(exc):
                raise SocialPublishError("x_refresh_failed", f"Secret Manager refresh token write failed: {_bounded_excerpt(str(exc))}") from exc
            try:
                client.create_secret(request=self._secret_create_request(ref))
                client.add_secret_version(request=request)
            except Exception as retry_exc:  # pragma: no cover - credential dependent
                if _is_gcp_adc_reauth_error(retry_exc):
                    raise SocialPublishError("gcp_adc_expired", _gcp_adc_reauth_summary()) from retry_exc
                raise SocialPublishError(
                    "x_refresh_failed",
                    f"Secret Manager refresh token write failed after creating secret: {_bounded_excerpt(str(retry_exc))}",
                ) from retry_exc


secret_store = SecretValueStore()


class XOAuth2TokenProvider:
    """Refresh X OAuth2 access tokens from long-lived Secret Manager credentials."""

    def __init__(self, store: SecretValueStore):
        self.store = store
        # Kept for backwards-compatible tests that clear runtime token state.
        # Access tokens are intentionally not cached across publish requests.
        self._cache: dict[str, tuple[str, float]] = {}

    def auth_status(self) -> tuple[str, str | None]:
        try:
            self.store.read(config.X_OAUTH_REFRESH_TOKEN_SECRET)
        except SocialPublishError as exc:
            if exc.kind == "gcp_adc_expired":
                return "gcp_adc_expired", exc.summary
            return "needs_authorization", exc.summary
        return "authorized", "OAuth refresh token is configured."

    def _client_credentials(self) -> tuple[str, str]:
        return (
            self.store.read(config.X_OAUTH_CLIENT_ID_SECRET),
            self.store.read(config.X_OAUTH_CLIENT_SECRET_SECRET),
        )

    def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        client_id, client_secret = self._client_credentials()
        payload = urllib.parse.urlencode({**form, "client_id": client_id}).encode("utf-8")
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
        request = urllib.request.Request(
            X_OAUTH_TOKEN_URL,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed X OAuth endpoint
                raw = response.read(8192).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read(4096).decode("utf-8", errors="replace")
            if exc.code in {400, 401, 403}:
                raise SocialPublishError("x_refresh_failed", f"X OAuth token exchange failed with HTTP {exc.code}: {_bounded_excerpt(raw)}") from exc
            raise SocialPublishError("x_refresh_failed", f"X OAuth token endpoint returned HTTP {exc.code}: {_bounded_excerpt(raw)}") from exc
        except Exception as exc:  # pragma: no cover - network dependent
            raise SocialPublishError("x_refresh_failed", f"X OAuth token request failed: {_bounded_excerpt(str(exc))}") from exc
        data = _json_loads(raw, {})
        if not isinstance(data, dict):
            raise SocialPublishError("x_refresh_failed", "X OAuth token response was not JSON.")
        return data

    def get_access_token(self, profile_ref: str = DEFAULT_X_SECRET_REF) -> XOAuth2AccessToken:
        ref = str(profile_ref or "").strip()
        if not ref:
            raise SocialPublishError("x_auth_failed", "X credential secret reference is empty.")
        if ref.startswith("env:"):
            return XOAuth2AccessToken(access_token=self.store.read(ref), refreshed=False)
        refresh_token = self.store.read(config.X_OAUTH_REFRESH_TOKEN_SECRET)
        data = self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})
        access_token = str(data.get("access_token") or "").strip()
        if not access_token:
            raise SocialPublishError("x_refresh_failed", "X OAuth refresh response did not include access_token.")
        new_refresh_token = str(data.get("refresh_token") or "").strip()
        rotated = False
        if new_refresh_token and new_refresh_token != refresh_token:
            self.store.add_version(config.X_OAUTH_REFRESH_TOKEN_SECRET, new_refresh_token)
            rotated = True
        return XOAuth2AccessToken(access_token=access_token, refreshed=True, refresh_token_rotated=rotated)

    def exchange_authorization_code(self, *, code: str, code_verifier: str, redirect_uri: str, profile_ref: str = DEFAULT_X_SECRET_REF) -> XOAuth2AccessToken:
        data = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            }
        )
        access_token = str(data.get("access_token") or "").strip()
        refresh_token = str(data.get("refresh_token") or "").strip()
        if not access_token:
            raise SocialPublishError("x_refresh_failed", "X OAuth callback response did not include access_token.")
        if not refresh_token:
            raise SocialPublishError("x_refresh_failed", "X OAuth callback response did not include refresh_token. Confirm offline.access scope is enabled.")
        self.store.add_version(config.X_OAUTH_REFRESH_TOKEN_SECRET, refresh_token)
        return XOAuth2AccessToken(access_token=access_token, refreshed=True, refresh_token_rotated=True)


x_oauth_token_provider = XOAuth2TokenProvider(secret_store)


def _read_secret_token(secret_ref: str) -> str:
    """Compatibility wrapper: return a short-lived OAuth2 access token."""

    request_token = _x_publish_access_token.get()
    if request_token and not str(secret_ref or "").strip().startswith("env:"):
        return request_token
    return x_oauth_token_provider.get_access_token(secret_ref).access_token


class XApiPublisher:
    """Narrow adapter for X API publishing.

    Tests replace this object; production reads Secret Manager only at publish time.
    """

    def _auth_failure_summary(self, action: str, raw: str, *, required_scope: str) -> str:
        excerpt = _bounded_excerpt(raw, max_chars=600)
        return f"X {action} authentication failed. Reconnect the X official account and approve the {required_scope} scope.{f' X response: {excerpt}' if excerpt else ''}"

    def _reply_forbidden_summary(self, raw: str) -> str:
        return f"X API does not allow this conversation reply. Reply manually on X, then mark the item as manually replied, or use quote/repost instead.{f' X response: {_bounded_excerpt(raw, max_chars=600)}' if raw else ''}"

    def upload_image(self, account: SocialAccountRow, image_path: str) -> str:
        token = _read_secret_token(account.secret_ref)
        path = Path(image_path)
        if not path.is_file():
            raise SocialPublishError("x_media_upload_failed", "Image asset file is missing; regenerate the image before publishing.")
        content_type = mimetypes.guess_type(str(path))[0] or "image/png"
        payload = json.dumps(
            {
                "media": base64.b64encode(path.read_bytes()).decode("ascii"),
                "media_category": "tweet_image",
                "media_type": content_type,
                "shared": False,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            X_MEDIA_UPLOAD_URL,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed X media endpoint
                raw = response.read(8192).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read(4096).decode("utf-8", errors="replace")
            if exc.code in {401, 403}:
                raise SocialPublishError("x_media_upload_auth_failed", self._auth_failure_summary("media upload", raw, required_scope="media.write")) from exc
            if exc.code == 429:
                raise SocialPublishError("x_rate_limited", "X media upload rate limit reached. Try again after the rate-limit window.") from exc
            raise SocialPublishError("x_media_upload_failed", f"X media upload returned HTTP {exc.code}: {_bounded_excerpt(raw)}") from exc
        except Exception as exc:  # pragma: no cover - network/credential dependent
            raise SocialPublishError("x_media_upload_failed", f"X media upload failed: {_bounded_excerpt(str(exc))}") from exc
        data = _json_loads(raw, {})
        data_obj = (data.get("data") if isinstance(data, dict) else {}) or {}
        media_id = str(
            (data_obj.get("id") if isinstance(data_obj, dict) else "")
            or (data_obj.get("media_id") if isinstance(data_obj, dict) else "")
            or (data_obj.get("media_key") if isinstance(data_obj, dict) else "")
            or (data.get("media_id_string") if isinstance(data, dict) else "")
            or (data.get("media_id") if isinstance(data, dict) else "")
            or ""
        ).strip()
        if not media_id:
            raise SocialPublishError("x_media_upload_failed", "X media upload response did not include media_id.")
        return media_id

    def publish_text(self, account: SocialAccountRow, body_text: str, media_ids: list[str] | None = None) -> XPublishResult:
        token = _read_secret_token(account.secret_ref)
        payload_obj: dict[str, Any] = {"text": body_text}
        if media_ids:
            payload_obj["media"] = {"media_ids": media_ids}
        payload = json.dumps(payload_obj, ensure_ascii=False).encode("utf-8")
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
                raise SocialPublishError("x_publish_auth_failed", self._auth_failure_summary("publish", raw, required_scope="tweet.write")) from exc
            if exc.code == 429:
                raise SocialPublishError("x_rate_limited", "X API rate limit reached. Try again after the rate-limit window.") from exc
            raise SocialPublishError("x_api_failed", f"X API returned HTTP {exc.code}: {_bounded_excerpt(raw)}") from exc
        except Exception as exc:  # pragma: no cover - network/credential dependent
            raise SocialPublishError("x_api_failed", f"X publish request failed: {_bounded_excerpt(str(exc))}") from exc
        data = _json_loads(raw, {})
        post_id = str(((data.get("data") if isinstance(data, dict) else {}) or {}).get("id") or "").strip()
        if not post_id:
            raise SocialPublishError("x_api_failed", "X API response did not include a post id.")
        return XPublishResult(post_id=post_id, response_summary={"data": {"id": post_id}, "media_ids": media_ids or []})

    def publish_reply(self, account: SocialAccountRow, body_text: str, *, in_reply_to_tweet_id: str) -> XPublishResult:
        token = _read_secret_token(account.secret_ref)
        reply_to = str(in_reply_to_tweet_id or "").strip()
        if not reply_to:
            raise SocialPublishError("x_reply_failed", "X reply target tweet id is missing.")
        payload_obj: dict[str, Any] = {
            "text": body_text,
            "reply": {"in_reply_to_tweet_id": reply_to},
        }
        payload = json.dumps(payload_obj, ensure_ascii=False).encode("utf-8")
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
                if exc.code == 403 and "reply to this conversation is not allowed" in raw.lower():
                    raise SocialPublishError("x_reply_conversation_forbidden", self._reply_forbidden_summary(raw)) from exc
                raise SocialPublishError("x_reply_auth_failed", self._auth_failure_summary("reply", raw, required_scope="tweet.write")) from exc
            if exc.code == 429:
                raise SocialPublishError("x_rate_limited", "X reply rate limit reached. Try again after the rate-limit window.") from exc
            raise SocialPublishError("x_reply_failed", f"X reply API returned HTTP {exc.code}: {_bounded_excerpt(raw)}") from exc
        except Exception as exc:  # pragma: no cover - network/credential dependent
            raise SocialPublishError("x_reply_failed", f"X reply request failed: {_bounded_excerpt(str(exc))}") from exc
        data = _json_loads(raw, {})
        post_id = str(((data.get("data") if isinstance(data, dict) else {}) or {}).get("id") or "").strip()
        if not post_id:
            raise SocialPublishError("x_reply_failed", "X reply API response did not include a post id.")
        return XPublishResult(post_id=post_id, response_summary={"data": {"id": post_id}, "reply_to": reply_to})


x_publisher: XApiPublisher = XApiPublisher()


def _publisher_uses_real_x_http() -> bool:
    return getattr(getattr(x_publisher, "publish_text", None), "__func__", None) is XApiPublisher.publish_text


def publish_social_post_to_x(db: Session, post_id: int, body: SocialPostPublishRequest) -> SocialPostDraftOut:
    row = _get_post(db, post_id)
    if row.platform != "x":
        raise ValueError("only X publishing is supported in v1")
    if row.status not in {"approved", "failed"}:
        raise ValueError("only approved or failed social drafts can be published to X")
    policy = run_content_policy_check(row.body_text)
    row.policy_check_json = _json_dumps(policy)
    if policy["status"] != "passed":
        raise ValueError("blocked social content cannot be published")
    media_assets = sorted(getattr(row, "media_assets", []) or [], key=lambda asset: int(asset.id or 0))
    active_image_assets = [asset for asset in media_assets if asset.media_type == "image" and asset.status != "removed"]
    failed_images = [asset for asset in active_image_assets if asset.status == "failed"]
    if failed_images:
        raise ValueError("image media failed; regenerate or remove the image before publishing")
    pending_images = [asset for asset in active_image_assets if asset.status not in {"ready", "uploaded"}]
    if pending_images:
        raise ValueError("image media is not ready yet")
    row.status = "publishing"
    row.failure_summary = None
    _record_event(db, row, "publish_requested", actor=body.actor, summary="Human requested X publish.")
    db.commit()
    db.refresh(row)
    token_context = None
    try:
        if _publisher_uses_real_x_http():
            token_result = x_oauth_token_provider.get_access_token(row.account.secret_ref)
            token_context = _x_publish_access_token.set(token_result.access_token)
            if token_result.refreshed:
                _record_event(
                    db,
                    row,
                    "x_token_refreshed",
                    actor=body.actor,
                    summary="Refreshed X OAuth2 access token for this publish attempt.",
                    payload={"refresh_token_rotated": token_result.refresh_token_rotated},
                )
        media_ids: list[str] = []
        for media in active_image_assets:
            if media.x_media_id:
                media_ids.append(media.x_media_id)
                continue
            media_id = x_publisher.upload_image(row.account, str(media.local_path or ""))
            media.x_media_id = media_id
            media.status = "uploaded"
            media_ids.append(media_id)
            _record_event(
                db,
                row,
                "media_uploaded_to_x",
                actor=body.actor,
                summary=f"Uploaded image media asset {int(media.id)} to X.",
                payload={"media_asset_id": int(media.id), "x_media_id": media_id},
            )
        result = x_publisher.publish_text(row.account, row.body_text, media_ids=media_ids) if media_ids else x_publisher.publish_text(row.account, row.body_text)
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
    finally:
        if token_context is not None:
            _x_publish_access_token.reset(token_context)

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


def publish_social_repost_candidate_to_x(
    db: Session,
    candidate_id: int,
    body: SocialRepostPublishRequest,
) -> SocialRepostCandidateOut:
    """Human-gated quote/repost action for a retained X candidate.

    v1 uses the same official X post API as normal publishing. A "quote" posts
    the proposed quote plus the source URL; a "repost" posts the source URL.
    Native retweet/quote APIs can be added later behind the same Human Gate.
    """

    candidate = db.get(SocialRepostCandidateRow, candidate_id)
    if candidate is None:
        raise ValueError("social repost candidate not found")
    if candidate.platform != "x":
        raise ValueError("only X repost candidates are supported in v1")
    action = str(body.action or "quote").strip().lower()
    if action not in {"quote", "repost"}:
        raise ValueError("unsupported repost action")
    if candidate.status not in {"candidate", "failed"}:
        raise ValueError("only candidate or failed repost candidates can be published")
    source_url = str(candidate.source_url or "").strip()
    if not source_url:
        raise ValueError("repost candidate requires a source URL")
    suggested_quote = str(candidate.suggested_quote or "").strip()
    if action == "quote" and not suggested_quote:
        raise ValueError("quote publish requires suggested quote text")

    body_text = f"{suggested_quote}\n\n{source_url}" if action == "quote" else source_url
    policy = run_content_policy_check(body_text)
    if policy["status"] != "passed":
        candidate.status = "failed"
        candidate.updated_at = utcnow()
        db.commit()
        raise ValueError("blocked repost candidate cannot be published")

    account = ensure_default_social_account(db)
    candidate.status = "publishing"
    candidate.updated_at = utcnow()
    post = SocialPostDraftRow(
        platform="x",
        account_id=int(account.id),
        source_type="repost_candidate",
        title=f"{'Quote' if action == 'quote' else 'Repost'}: @{candidate.author_handle or 'unknown'}",
        body_text=body_text,
        status="approved",
        generated_by="x_social_repost_candidate_sweep",
        reviewed_by=body.actor,
        policy_check_json=_json_dumps(policy),
        raw_agent_output_json=_json_dumps(
            {
                "repost_candidate_id": int(candidate.id),
                "repost_action": action,
                "source_url": source_url,
                "author_handle": candidate.author_handle,
                "human_gate_required": True,
            }
        ),
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    published_post = publish_social_post_to_x(db, int(post.id), SocialPostPublishRequest(actor=body.actor))
    candidate = db.get(SocialRepostCandidateRow, candidate_id)
    if candidate is None:
        raise ValueError("social repost candidate not found")
    candidate.status = "published" if published_post.status == "published" else "failed"
    candidate.updated_at = utcnow()
    db.commit()
    db.refresh(candidate)
    return _repost_candidate_out(candidate)


def generate_social_reply_for_repost_candidate(
    db: Session,
    candidate_id: int,
    body: SocialReplyPublishRequest | SocialPostPublishRequest,
) -> SocialReplyItemOut:
    candidate = db.get(SocialRepostCandidateRow, candidate_id)
    if candidate is None:
        raise ValueError("social repost candidate not found")
    if candidate.status not in {"candidate", "failed"}:
        raise ValueError("only active repost candidates can generate reply drafts")
    row = _create_reply_from_repost_candidate(
        db,
        candidate,
        actor=getattr(body, "actor", "operator") or "operator",
        force_regenerate=True,
    )
    db.commit()
    db.refresh(row)
    return _social_reply_out(row)


def regenerate_unpublished_social_replies_with_agent(db: Session, *, actor: str = "operator") -> dict[str, Any]:
    """Regenerate non-settled reply drafts with the real reply agent.

    Published and rejected records are audit results and are intentionally left
    untouched. Each row is handled independently so one provider failure does
    not hide the remaining rows that still need review.
    """

    rows = (
        db.query(SocialReplyItemRow)
        .filter(SocialReplyItemRow.status.in_(["needs_review", "failed", "approved"]))
        .order_by(SocialReplyItemRow.id.asc())
        .all()
    )
    regenerated_ids: list[int] = []
    failed_ids: list[int] = []
    skipped_ids: list[int] = []
    for row in rows:
        candidate = db.get(SocialRepostCandidateRow, row.source_candidate_id) if row.source_candidate_id else None
        if candidate is None:
            skipped_ids.append(int(row.id))
            continue
        updated = _create_reply_from_repost_candidate(
            db,
            candidate,
            actor=actor,
            force_regenerate=True,
        )
        if updated.status == "failed":
            failed_ids.append(int(updated.id))
        else:
            regenerated_ids.append(int(updated.id))
        db.commit()
    return {
        "regenerated_ids": regenerated_ids,
        "failed_ids": failed_ids,
        "skipped_ids": skipped_ids,
        "processed_count": len(regenerated_ids) + len(failed_ids),
    }


def update_social_reply(db: Session, reply_id: int, body: SocialReplyPatchRequest) -> SocialReplyItemOut:
    row = db.get(SocialReplyItemRow, reply_id)
    if row is None:
        raise ValueError("social reply item not found")
    if row.status in {"published", "published_manual"}:
        raise ValueError("published replies cannot be edited")
    if body.suggested_reply is not None:
        row.suggested_reply = str(body.suggested_reply or "").strip()
    if body.status is not None:
        status = str(body.status or "").strip()
        if status not in {"needs_review", "approved", "failed", "rejected", "published_manual"}:
            raise ValueError("unsupported reply status")
        row.status = status
        row.reviewed_by = body.reviewed_by
        if status == "published_manual":
            row.failure_summary = None
            row.published_external_post_id = row.published_external_post_id or f"manual:{row.source_post_id or int(row.id)}"
    if body.review_note:
        metadata = _json_loads(row.metadata_json, {})
        metadata["review_note"] = str(body.review_note)
        row.metadata_json = _json_dumps(metadata)
    if row.suggested_reply and row.status != "published_manual":
        policy = run_content_policy_check(row.suggested_reply)
        metadata = _json_loads(row.metadata_json, {})
        metadata["policy_check"] = policy
        row.metadata_json = _json_dumps(metadata)
        if policy["status"] != "passed":
            row.status = "failed"
            row.failure_summary = f"Blocked: {', '.join(policy['blocked_reasons'])}"
        elif row.status == "failed" and row.failure_summary and row.failure_summary.startswith("Blocked:"):
            row.status = "needs_review"
            row.failure_summary = None
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return _social_reply_out(row)


def publish_social_reply_to_x(db: Session, reply_id: int, body: SocialReplyPublishRequest) -> SocialReplyItemOut:
    row = db.get(SocialReplyItemRow, reply_id)
    if row is None:
        raise ValueError("social reply item not found")
    if row.platform != "x":
        raise ValueError("only X replies are supported in v1")
    if row.status not in {"needs_review", "approved", "failed"}:
        raise ValueError("only reviewable or failed replies can be published")
    reply_text = str(row.suggested_reply or "").strip()
    if not reply_text:
        raise ValueError("reply text is empty")
    source_post_id = str(row.source_post_id or "").strip() or _extract_x_post_id(row.source_url)
    if not source_post_id:
        raise ValueError("reply source tweet id is missing")
    policy = run_content_policy_check(reply_text)
    if policy["status"] != "passed":
        row.status = "failed"
        row.failure_summary = f"Blocked: {', '.join(policy['blocked_reasons'])}"
        row.updated_at = utcnow()
        db.commit()
        db.refresh(row)
        return _social_reply_out(row)
    account = ensure_default_social_account(db)
    row.status = "publishing"
    row.reviewed_by = body.actor
    row.failure_summary = None
    row.updated_at = utcnow()
    db.commit()

    token_context = None
    try:
        token_result = x_oauth_token_provider.get_access_token(account.secret_ref)
        token_context = _x_publish_access_token.set(token_result.access_token)
        result = x_publisher.publish_reply(account, reply_text, in_reply_to_tweet_id=source_post_id)
    except SocialPublishError as exc:
        row = db.get(SocialReplyItemRow, reply_id)
        if row is None:
            raise ValueError("social reply item not found") from exc
        row.status = "failed"
        row.failure_summary = exc.summary
        row.updated_at = utcnow()
        metadata = _json_loads(row.metadata_json, {})
        metadata["publish_failure_kind"] = exc.kind
        row.metadata_json = _json_dumps(metadata)
        db.commit()
        db.refresh(row)
        return _social_reply_out(row)
    finally:
        if token_context is not None:
            _x_publish_access_token.reset(token_context)

    row = db.get(SocialReplyItemRow, reply_id)
    if row is None:
        raise ValueError("social reply item not found")
    row.status = "published"
    row.external_reply_id = result.post_id
    row.published_external_post_id = result.post_id
    row.failure_summary = None
    row.updated_at = utcnow()
    metadata = _json_loads(row.metadata_json, {})
    metadata.update(
        {
            "published_by": body.actor,
            "response_summary": result.response_summary,
            "reply_to": source_post_id,
        }
    )
    row.metadata_json = _json_dumps(metadata)
    candidate_id = int(row.source_candidate_id or 0)
    if candidate_id:
        candidate = db.get(SocialRepostCandidateRow, candidate_id)
        if candidate is not None and candidate.status == "candidate":
            candidate.status = "replied"
            candidate.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return _social_reply_out(row)
