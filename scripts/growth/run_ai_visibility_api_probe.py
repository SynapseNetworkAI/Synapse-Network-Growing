#!/usr/bin/env python3
"""Run paid answer-engine API probes and emit Growing AI visibility JSONL rows.

The runner is fail-closed by default: it prints provider/key readiness without
calling paid APIs unless --execute is present. It never logs API key values.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.growth import ai_visibility_api_probe_adapters as probe_adapters  # noqa: E402
from scripts.growth.ai_visibility_api_probe_failures import (  # noqa: E402
    provider_failure_payload,
)
from scripts.growth.ai_visibility_api_probe_records import (  # noqa: E402
    api_readiness_blocker_records,
)
from scripts.growth.ai_visibility_cli import emit_failure, write_text_or_stdout  # noqa: E402
from scripts.growth.generate_ai_visibility_probe_template import (  # noqa: E402
    DEFAULT_FEED_KEY,
    default_queries_for_feed,
    official_source_urls_for_feed,
    parse_platforms,
    template_record,
)
from scripts.growth.local_env import load_optional_dotenv_path  # noqa: E402
from scripts.growth.record_ai_visibility_probe import (  # noqa: E402
    record_from_payload,
    validate_records,
)

DEFAULT_PLATFORMS = probe_adapters.API_DEFAULT_PLATFORMS
DEFAULT_MODELS = probe_adapters.DEFAULT_MODELS
ENV_KEYS = probe_adapters.ENV_KEYS
ENV_KEY_ALIASES = probe_adapters.ENV_KEY_ALIASES
OPENAI_RESPONSES_URL = probe_adapters.OPENAI_RESPONSES_URL
answer_payload = probe_adapters.answer_payload
api_key_for_platform = probe_adapters.api_key_for_platform
call_gemini = probe_adapters.call_gemini
call_platform = probe_adapters.call_platform
platform_api_key = probe_adapters.api_key_for_platform
post_json = probe_adapters.post_json
redact_secrets = probe_adapters.redact_secrets
source_hosts = probe_adapters.source_hosts


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Run fail-closed API probes for ChatGPT, Claude, Grok, and Gemini."
    )
    parser.add_argument("--feed-key", default=DEFAULT_FEED_KEY)
    parser.add_argument(
        "--run-group",
        default=f"{datetime.now(UTC).date().isoformat()}-api-probe",
    )
    parser.add_argument(
        "--platforms",
        default=",".join(DEFAULT_PLATFORMS),
        help="Comma-separated platforms. Supported API probes: chatgpt,claude,grok,gemini.",
    )
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="Question to run. Repeat for multiple queries. Defaults to the selected feed target queries.",
    )
    parser.add_argument("--output", help="Write JSONL probe rows to this path.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually call paid answer-engine APIs. Without this flag, only readiness is reported.",
    )
    parser.add_argument(
        "--env-file",
        help=(
            "Optional dotenv file for local API keys. Also supported through "
            "AI_VISIBILITY_ENV_FILE. Key values are never printed."
        ),
    )
    args = parser.parse_args()

    try:
        env_file_loaded = load_optional_dotenv_path(
            args.env_file or os.environ.get("AI_VISIBILITY_ENV_FILE", "")
        )
        platforms = parse_api_platforms(args.platforms)
        queries = args.queries or default_queries_for_feed(args.feed_key)
        missing = missing_key_blockers(platforms)
        if missing:
            rows = api_readiness_blocker_records(
                feed_key=args.feed_key,
                run_group=args.run_group,
                missing=missing,
                query_count=len(queries),
            )
            errors = validate_records(rows)
            if errors:
                emit({"status": "failed", "errors": errors}, stderr=True)
                return 2
            if args.output:
                payload = "\n".join(
                    json.dumps(row.api_payload(), ensure_ascii=False) for row in rows
                )
                write_text_or_stdout(payload, output=args.output)
            emit_status(
                platforms=platforms,
                queries=queries,
                missing=missing,
                execute=args.execute,
                output=args.output,
                env_file_loaded=env_file_loaded,
            )
            return 2 if args.execute and missing else 0

        if not args.execute:
            emit_status(
                platforms=platforms,
                queries=queries,
                missing=missing,
                execute=args.execute,
                output=args.output,
                env_file_loaded=env_file_loaded,
            )
            return 0

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
            "API runner supports only chatgpt, claude, grok, and gemini; unsupported: "
            + ", ".join(unsupported)
        )
    return platforms


def missing_key_blockers(platforms: Iterable[str]) -> list[Any]:
    blockers = []
    for platform in platforms:
        env_keys = ENV_KEY_ALIASES.get(platform, (ENV_KEYS[platform],))
        if not platform_api_key(platform):
            missing_env = " or ".join(env_keys)
            blockers.append({"platform": platform, "missing_env": missing_env})
    return blockers


def emit_status(
    *,
    platforms: list[str],
    queries: list[str],
    missing: list[dict[str, str]],
    execute: bool,
    output: str | None,
    env_file_loaded: bool,
) -> None:
    emit(
        {
            "status": "blocked" if missing else "ready",
            "execute": execute,
            "env_file_loaded": env_file_loaded,
            "platforms": platforms,
            "query_count": len(queries),
            "missing": missing,
            "output": output or "",
            "record_count": len(missing) if missing and output else 0,
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
    official_source_urls = official_source_urls_for_feed(feed_key)
    for query in queries:
        for platform in platforms:
            template = template_record(
                query=query,
                platform=platform,
                feed_key=feed_key,
                run_group=run_group,
                mode="after-feed",
                generated_at=datetime.now(UTC).date().isoformat(),
                official_source_urls=official_source_urls,
            )
            answer = call_platform_with_failure_boundary(platform, query)
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
                    "evidence_url": "",
                    "metadata": {
                        **payload["metadata"],
                        "mode": "api_probe",
                        "evidence_capture": (
                            "API probe evidence is this JSONL row plus "
                            "api_request_id; no screenshot was captured."
                        ),
                        "api_model": answer["model"],
                        "api_request_id": answer["request_id"],
                        "source_url_count": str(len(answer["source_urls"])),
                        "source_hosts": source_hosts(answer["source_urls"])[:12],
                        "synapse_cited_url_count": str(len(answer["cited_urls"])),
                    },
                }
            )
            rows.append(record_from_payload(payload, index=len(rows)))
    return rows


def call_platform_with_failure_boundary(platform: str, query: str) -> Any:
    try:
        return call_platform(platform, query)
    except Exception as exc:  # noqa: BLE001 - provider adapters must fail bounded
        return provider_failure_payload(
            platform=platform,
            query=query,
            default_models=DEFAULT_MODELS,
            redacted_error=redact_secrets(str(exc)),
        )


def emit(payload: dict[str, Any], *, stderr: bool = False) -> None:
    print(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        file=sys.stderr if stderr else sys.stdout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
