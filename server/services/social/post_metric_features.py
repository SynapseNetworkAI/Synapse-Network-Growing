"""Feature extraction helpers for X post metrics."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from server.database import SocialPostMetricRow

_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
_TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("agent_payments", ("payment", "settlement", "usdc", "x402")),
    ("local_runner", ("local runner", "deploy runner", "github actions", "ci")),
    ("provider_registry", ("provider registry", "onboarding", "provider")),
    ("budget_caps", ("budget", "spend cap", "runaway spend", "$5")),
    ("sdk", ("sdk", "pypi", "npm", "maven", "nuget")),
    ("human_gate", ("human gate", "blast radius", "fail closed")),
)


@dataclass(frozen=True)
class MetricTarget:
    source_kind: str
    post_id: int | None
    task_id: int | None
    external_post_id: str
    title: str | None
    body_text: str
    status: str | None
    published_at: Any
    metadata: dict[str, Any]


def json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def json_object(raw: str | None) -> Any:
    payload = json_loads(raw, {})
    return payload if isinstance(payload, dict) else {}


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def metadata_int(metadata: Mapping[str, Any], key: str) -> int:
    try:
        return max(0, int(metadata.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def metric_value(*maps: dict[str, Any] | None, keys: tuple[str, ...]) -> int:
    for payload in maps:
        if not isinstance(payload, dict):
            continue
        for key in keys:
            try:
                return int(payload.get(key) or 0)
            except (TypeError, ValueError):
                continue
    return 0


def metric_metadata(row: SocialPostMetricRow) -> Mapping[str, Any]:
    return json_object(getattr(row, "metadata_json", None))


def first_line(value: str | None, *, max_chars: int = 160) -> str | None:
    for line in str(value or "").splitlines():
        text = " ".join(line.split()).strip()
        if text:
            return text[:max_chars]
    return None


def topic_tags_for_text(
    text: str, metadata: Mapping[str, Any] | None = None
) -> list[str]:
    existing = (metadata or {}).get("topic_tags")
    if isinstance(existing, list) and existing:
        return sorted({str(item) for item in existing if str(item).strip()})
    lowered = str(text or "").lower()
    return sorted(
        tag for tag, tokens in _TOPIC_RULES if any(token in lowered for token in tokens)
    )


def _format_kind(target: MetricTarget, metadata: Mapping[str, Any]) -> str:
    return str(
        metadata.get("format_kind")
        or metadata.get("x_format")
        or ("reply" if target.source_kind == "reply" else "single")
    )


def _post_intent(target: MetricTarget, metadata: Mapping[str, Any]) -> str | None:
    return (
        metadata.get("post_intent")
        or metadata.get("intent")
        or ("engagement_reply" if target.source_kind == "reply" else None)
    )


def _source_strategy(metadata: Mapping[str, Any]) -> Any:
    return (
        metadata.get("source_strategy")
        or metadata.get("x_reply_source_strategy")
        or metadata.get("reply_source_strategy")
    )


def _content_type(target: MetricTarget, metadata: Mapping[str, Any]) -> str:
    return str(
        metadata.get("content_type")
        or ("reply" if target.source_kind == "reply" else "original")
    )


def _has_url(metadata: Mapping[str, Any], body: str) -> bool:
    return bool(metadata.get("has_url")) or bool(_URL_PATTERN.search(body))


def _has_media(metadata: Mapping[str, Any]) -> bool:
    return bool(metadata.get("has_media") or metadata.get("media_assets"))


def _has_thread(metadata: Mapping[str, Any], format_kind: str) -> bool:
    return bool(metadata.get("has_thread") or format_kind == "thread")


def metric_metadata_for_target(
    target: MetricTarget,
    *,
    x_post: Any | None = None,
    private_metrics_available: bool | None = None,
    metric_source: str = "x_api",
    extra: Mapping[str, Any] | None = None,
) -> Any:
    metadata = dict(target.metadata or {})
    body = target.body_text or getattr(x_post, "text", "") or ""
    format_kind = _format_kind(target, metadata)
    has_url = _has_url(metadata, body)
    payload = {
        "content_type": _content_type(target, metadata),
        "format_kind": format_kind,
        "post_intent": _post_intent(target, metadata),
        "source_strategy": _source_strategy(metadata),
        "hook_text": metadata.get("hook_text") or first_line(body),
        "topic_tags": topic_tags_for_text(body, metadata),
        "has_media": _has_media(metadata),
        "has_thread": _has_thread(metadata, format_kind),
        "has_url": has_url,
        "human_link_reason": metadata.get("human_link_reason"),
        "negative_feedback_count": metadata_int(metadata, "negative_feedback_count"),
        "subscription_conversions": metadata_int(metadata, "subscription_conversions"),
        "metric_source": metric_source,
        "private_metrics_available": bool(private_metrics_available),
        "source_kind": target.source_kind,
        "distribution_task_id": target.task_id,
    }
    if not has_url:
        payload["link_click_policy"] = "no_url_post_link_clicks_are_zero"
    if extra:
        payload.update(extra)
    return payload
