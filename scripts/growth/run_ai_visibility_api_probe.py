#!/usr/bin/env python3
"""Run paid answer-engine API probes and emit Growing AI visibility JSONL rows.

The runner is fail-closed by default: it prints provider/key readiness without
calling paid APIs unless --execute is present. It never logs API key values.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.growth.ai_visibility_cli import emit_failure, write_text_or_stdout  # noqa: E402
from scripts.growth.generate_ai_visibility_probe_template import (  # noqa: E402
    DEFAULT_FEED_KEY,
    DEFAULT_PLATFORMS,
    baseline_queries,
    parse_platforms,
    template_record,
)
from scripts.growth.record_ai_visibility_probe import (  # noqa: E402
    record_from_payload,
    validate_records,
)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"

DEFAULT_MODELS = {
    "chatgpt": "gpt-4o-mini",
    "claude": "claude-3-7-sonnet-latest",
    "grok": "grok-4.20-reasoning",
}

ENV_KEYS = {
    "chatgpt": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "grok": "XAI_API_KEY",
}


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Run fail-closed API probes for ChatGPT, Claude, and Grok."
    )
    parser.add_argument("--feed-key", default=DEFAULT_FEED_KEY)
    parser.add_argument(
        "--run-group",
        default=f"{datetime.now(UTC).date().isoformat()}-api-probe",
    )
    parser.add_argument(
        "--platforms",
        default=",".join(DEFAULT_PLATFORMS),
        help="Comma-separated platforms. Supported API probes: chatgpt,claude,grok.",
    )
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="Question to run. Repeat for multiple queries. Defaults to baseline queries.",
    )
    parser.add_argument("--output", help="Write JSONL probe rows to this path.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually call paid answer-engine APIs. Without this flag, only readiness is reported.",
    )
    args = parser.parse_args()

    try:
        platforms = parse_api_platforms(args.platforms)
        queries = args.queries or baseline_queries()
        missing = missing_key_blockers(platforms)
        if missing or not args.execute:
            emit_status(
                platforms=platforms,
                queries=queries,
                missing=missing,
                execute=args.execute,
            )
            return 2 if args.execute and missing else 0

        rows = run_api_probes(
            feed_key=args.feed_key,
            run_group=args.run_group,
            platforms=platforms,
            queries=queries,
        )
        errors = validate_records(rows)
        if errors:
            emit({"status": "failed", "errors": errors}, stderr=True)
            return 2
        payload = "\n".join(
            json.dumps(row.api_payload(), ensure_ascii=False) for row in rows
        )
        write_text_or_stdout(payload, output=args.output)
        return 0
    except Exception as exc:
        emit_failure(exc)
        return 1


def parse_api_platforms(raw: str) -> list[str]:
    platforms = parse_platforms(raw)
    unsupported = [item for item in platforms if item not in ENV_KEYS]
    if unsupported:
        raise ValueError(
            "API runner supports only chatgpt, claude, and grok; unsupported: "
            + ", ".join(unsupported)
        )
    return platforms


def missing_key_blockers(platforms: Iterable[str]) -> list[Any]:
    blockers = []
    for platform in platforms:
        env_key = ENV_KEYS[platform]
        if not os.environ.get(env_key, "").strip():
            blockers.append({"platform": platform, "missing_env": env_key})
    return blockers


def emit_status(
    *,
    platforms: list[str],
    queries: list[str],
    missing: list[dict[str, str]],
    execute: bool,
) -> None:
    emit(
        {
            "status": "blocked" if missing else "ready",
            "execute": execute,
            "platforms": platforms,
            "query_count": len(queries),
            "missing": missing,
            "message": (
                "Set missing API keys and rerun with --execute to call paid probes."
                if missing
                else "Ready. Rerun with --execute to call paid probes."
            ),
        }
    )


def run_api_probes(  # pragma: no cover - paid external API adapter
    *,
    feed_key: str,
    run_group: str,
    platforms: list[str],
    queries: list[str],
):
    rows = []
    for query in queries:
        for platform in platforms:
            template = template_record(
                query=query,
                platform=platform,
                feed_key=feed_key,
                run_group=run_group,
                mode="after-feed",
                generated_at=datetime.now(UTC).date().isoformat(),
            )
            answer = call_platform(platform, query)
            payload = asdict(template)
            payload.update(
                {
                    "answer_summary": answer["summary"],
                    "synapse_mentioned": answer["synapse_mentioned"],
                    "synapse_cited": answer["synapse_cited"],
                    "cited_urls": answer["cited_urls"],
                    "competitor_mentions": answer["competitor_mentions"],
                    "missing_facts": answer["missing_facts"],
                    "next_action": answer["next_action"],
                    "result_rank": answer["result_rank"],
                    "metadata": {
                        **payload["metadata"],
                        "mode": "api_probe",
                        "api_model": answer["model"],
                        "api_request_id": answer["request_id"],
                        "source_url_count": str(len(answer["source_urls"])),
                        "synapse_cited_url_count": str(len(answer["cited_urls"])),
                    },
                }
            )
            rows.append(record_from_payload(payload, index=len(rows)))
    return rows


def call_platform(
    platform: str, query: str
) -> Any:  # pragma: no cover - adapter dispatch
    if platform == "chatgpt":
        return call_openai(query)
    if platform == "claude":
        return call_anthropic(query)
    if platform == "grok":
        return call_xai(query)
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


def extract_urls(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        for key, next_value in value.items():
            if key in {"url", "uri"} and isinstance(next_value, str):
                urls.append(next_value)
            else:
                urls.extend(extract_urls(next_value))
    elif isinstance(value, list):
        for item in value:
            urls.extend(extract_urls(item))
    return sorted({url for url in urls if url.startswith("http")})


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
    return any(
        host in url
        for host in (
            "www.synapse-network.ai",
            "docs.synapse-network.ai",
            "github.com/SynapseNetworkAI",
            "mcp.synapse-network.ai",
            "registry.modelcontextprotocol.io",
        )
    )


def competitor_mentions(text: str, urls: list[str]) -> list[str]:
    haystack = " ".join([text, *urls]).lower()
    competitors = []
    for label in ["x402", "stripe", "rapidapi", "masumi", "locus", "payspawn"]:
        if re.search(rf"\b{re.escape(label)}\b", haystack):
            competitors.append(label)
    return competitors


def redact_secrets(value: str) -> str:
    redacted = value
    for env_key in ENV_KEYS.values():
        secret_value = os.environ.get(env_key, "").strip()
        if secret_value:
            redacted = redacted.replace(secret_value, "[REDACTED]")
    return redacted


def emit(payload: dict[str, Any], *, stderr: bool = False) -> None:
    print(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        file=sys.stderr if stderr else sys.stdout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
