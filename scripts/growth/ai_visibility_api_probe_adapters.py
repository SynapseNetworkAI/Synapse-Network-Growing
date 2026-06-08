"""Paid answer-engine API adapters for AI visibility probes."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from scripts.growth.generate_ai_visibility_probe_template import KNOWN_COLLISION_DOMAINS
from server.services.growth.ai_visibility_official_sources import is_official_citation_url

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"
GEMINI_GENERATE_CONTENT_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
API_DEFAULT_PLATFORMS = ["chatgpt", "claude", "grok", "gemini"]

DEFAULT_MODELS = {
    "chatgpt": "gpt-4o-mini",
    "claude": "claude-sonnet-4-6",
    "grok": "grok-4.20-reasoning",
    "gemini": "gemini-2.5-flash",
}

ENV_KEYS = {
    "chatgpt": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "grok": "XAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
ENV_KEY_ALIASES = {
    "gemini": ("GEMINI_API_KEY", "GENIMI_API_KEY"),
}
KNOWN_PAID_MCP_COMPETITORS = [
    "x402",
    "stripe",
    "rapidapi",
    "masumi",
    "locus",
    "payspawn",
    "mcpay",
    "latch",
    "dock0",
    "apiosk",
    "teleport",
    "magpie",
    "whop",
    "mseep",
    "gapup",
    "lobehub",
    "mcpservers.org",
    "mcphub",
    "composio",
    "n8n",
]


def call_platform(
    platform: str, query: str
) -> Any:  # pragma: no cover - adapter dispatch
    if platform == "chatgpt":
        return call_openai(query)
    if platform == "claude":
        return call_anthropic(query)
    if platform == "grok":
        return call_xai(query)
    if platform == "gemini":
        return call_gemini(query)
    raise ValueError(f"unsupported platform: {platform}")


def call_openai(query: str) -> Any:  # pragma: no cover - paid external API adapter
    model = os.environ.get("OPENAI_AI_VISIBILITY_MODEL", DEFAULT_MODELS["chatgpt"])
    payload = {
        "model": model,
        "tools": [{"type": "web_search"}],
        "tool_choice": "auto",
        "include": ["web_search_call.action.sources"],
        "input": prompt_for_query(query),
    }
    data, request_id = post_json(
        OPENAI_RESPONSES_URL,
        payload,
        {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
    )
    text = data.get("output_text") or extract_openai_text(data)
    urls = extract_urls(data)
    return answer_payload(
        platform="chatgpt",
        model=model,
        text=text,
        urls=urls,
        request_id=request_id,
    )


def call_anthropic(query: str) -> Any:  # pragma: no cover - paid external API adapter
    model = os.environ.get("ANTHROPIC_AI_VISIBILITY_MODEL", DEFAULT_MODELS["claude"])
    payload = {
        "model": model,
        "max_tokens": 900,
        "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        "messages": [{"role": "user", "content": prompt_for_query(query)}],
    }
    data, request_id = post_json(
        ANTHROPIC_MESSAGES_URL,
        payload,
        {
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        },
    )
    text = extract_anthropic_text(data)
    urls = extract_urls(data)
    return answer_payload(
        platform="claude",
        model=model,
        text=text,
        urls=urls,
        request_id=request_id,
    )


def call_xai(query: str) -> Any:  # pragma: no cover - paid external API adapter
    model = os.environ.get("XAI_AI_VISIBILITY_MODEL", DEFAULT_MODELS["grok"])
    payload = {
        "model": model,
        "input": [{"role": "user", "content": prompt_for_query(query)}],
        "tools": [{"type": "web_search"}],
    }
    data, request_id = post_json(
        XAI_RESPONSES_URL,
        payload,
        {"Authorization": f"Bearer {os.environ['XAI_API_KEY']}"},
    )
    text = data.get("output_text") or extract_openai_text(data)
    urls = extract_urls(data)
    return answer_payload(
        platform="grok",
        model=model,
        text=text,
        urls=urls,
        request_id=request_id,
    )


def call_gemini(query: str) -> Any:  # pragma: no cover - paid external API adapter
    model = os.environ.get("GEMINI_AI_VISIBILITY_MODEL", DEFAULT_MODELS["gemini"])
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt_for_query(query)}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 900},
    }
    data, request_id = post_json(
        GEMINI_GENERATE_CONTENT_URL.format(model=urllib.parse.quote(model, safe="")),
        payload,
        {"x-goog-api-key": api_key_for_platform("gemini")},
    )
    text = extract_gemini_text(data)
    urls = extract_urls(data)
    return answer_payload(
        platform="gemini",
        model=model,
        text=text,
        urls=urls,
        request_id=request_id or str(data.get("responseId") or ""),
    )


def api_key_for_platform(platform: str) -> str:
    for env_key in ENV_KEY_ALIASES.get(platform, (ENV_KEYS[platform],)):
        value = os.environ.get(env_key, "").strip()
        if value:
            return value
    return ""


def prompt_for_query(query: str) -> str:
    return (
        "Use live web search. Answer the question exactly as an answer engine would, "
        "with source citations when available. Question: "
        f"{query}"
    )


def post_json(
    url: str, payload: dict[str, Any], headers: dict[str, str]
) -> tuple[Any, str]:  # pragma: no cover - network adapter
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError("AI visibility API probes require https URLs")
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:  # nosec B310
            data = json.loads(response.read().decode("utf-8"))
            request_id = response.headers.get("request-id") or response.headers.get(
                "x-request-id", ""
            )
            return data, request_id
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        safe_body = redact_secrets(body[:500])
        raise RuntimeError(f"POST {url} failed with {exc.code}: {safe_body}") from exc


def extract_openai_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in data.get("output") or []:
        for content in item.get("content") or []:
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def extract_anthropic_text(data: dict[str, Any]) -> str:
    parts = []
    for item in data.get("content") or []:
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts).strip()


def extract_gemini_text(data: dict[str, Any]) -> str:
    parts = []
    for candidate in data.get("candidates") or []:
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def extract_urls(value: Any) -> list[str]:
    return sorted(
        {
            normalized
            for url in _extract_urls(value)
            if (normalized := normalize_extracted_url(url)).startswith("http")
        }
    )


def _extract_urls(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        for key, next_value in value.items():
            if key in {"url", "uri"} and isinstance(next_value, str):
                urls.append(next_value)
            urls.extend(_extract_urls(next_value))
    elif isinstance(value, list):
        for item in value:
            urls.extend(_extract_urls(item))
    elif isinstance(value, str):
        urls.extend(
            match.rstrip(").,;]")
            for match in re.findall(r"https?://[^\s)\]}>\"']+", value)
        )
    return urls


def normalize_extracted_url(url: str) -> str:
    candidate = url.strip().strip("<>")
    candidate = re.sub(r"(?:\.\*\*\[\[\d+|\*\*\[\[\d+|\[\[\d+)$", "", candidate)
    return candidate.rstrip("`*.,;)]")


def source_hosts(urls: list[str]) -> list[str]:
    hosts = []
    for url in urls:
        host = urllib.parse.urlsplit(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host:
            hosts.append(host)
    return sorted(set(hosts))


def answer_payload(
    *,
    platform: str,
    model: str,
    text: str,
    urls: list[str],
    request_id: str,
) -> dict[str, Any]:
    if not text.strip():
        raise RuntimeError(f"{platform} API returned no answer text")
    lowered = text.lower()
    cited_synapse_urls = [url for url in urls if is_synapse_url(url)]
    mentioned = "synapse network" in lowered or "synapsenetwork" in lowered
    competitors = competitor_mentions(text, urls)
    return {
        "summary": text[:1200],
        "synapse_mentioned": mentioned or bool(cited_synapse_urls),
        "synapse_cited": bool(cited_synapse_urls),
        "cited_urls": cited_synapse_urls,
        "source_urls": urls,
        "competitor_mentions": competitors,
        "missing_facts": [] if mentioned else ["Synapse Network was not mentioned."],
        "next_action": (
            "Compare against previous run group and keep feeding cited surfaces."
            if mentioned
            else "Deploy/refresh feed assets and rerun the same API probe."
        ),
        "result_rank": 1 if mentioned else 0,
        "model": model,
        "request_id": request_id,
        "platform": platform,
    }


def is_synapse_url(url: str) -> bool:
    return is_official_citation_url(normalize_extracted_url(url))


def competitor_mentions(text: str, urls: list[str]) -> list[str]:
    haystack = " ".join([text, *urls]).lower()
    competitors = []
    for label in KNOWN_PAID_MCP_COMPETITORS:
        if re.search(rf"\b{re.escape(label)}\b", haystack):
            competitors.append(label)
    for domain in KNOWN_COLLISION_DOMAINS:
        if collision_domain_mentioned(domain, haystack):
            competitors.append(domain)
    return competitors


def collision_domain_mentioned(domain: str, haystack: str) -> bool:
    lowered_domain = domain.lower()
    if "/" in lowered_domain:
        return lowered_domain in haystack
    escaped = re.escape(lowered_domain)
    return bool(re.search(rf"(?<![a-z0-9-]){escaped}(?![a-z0-9-])", haystack))


def redact_secrets(value: str) -> str:
    redacted = value
    env_keys = set(ENV_KEYS.values())
    for aliases in ENV_KEY_ALIASES.values():
        env_keys.update(aliases)
    for env_key in env_keys:
        secret_value = os.environ.get(env_key, "").strip()
        if secret_value:
            redacted = redacted.replace(secret_value, "[REDACTED]")
    return redacted
