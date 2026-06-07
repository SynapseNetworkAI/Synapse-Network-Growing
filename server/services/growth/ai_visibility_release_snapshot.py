"""Read-only AI visibility release blocker snapshot."""

from __future__ import annotations

import os
import subprocess  # nosec B404
from datetime import UTC, datetime
from typing import Any

from server.services.growth.ai_visibility_live_readiness import (
    ai_visibility_live_readiness,
)
from server.services.growth.ai_visibility_release_unblock import (
    DEFAULT_ACTOR,  # noqa: F401
    DEFAULT_TARGET_COMMIT,  # noqa: F401
    PRODUCTION_PROJECT_ID,
    STAGING_PROJECT_ID,
    build_release_unblock_plan,
)
from server.services.growth.ai_visibility_text import unique_strings

API_ENV_KEYS = {
    "chatgpt": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "grok": "XAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
API_ENV_KEY_ALIASES = {
    "gemini": ("GEMINI_API_KEY", "GENIMI_API_KEY"),
}


def build_snapshot(
    *,
    target_commit: str,
    actor: str,
    feed_key: str,
    run_group: str,
) -> dict[str, Any]:
    generated_at = datetime.now(UTC).isoformat()
    safe_run_group = run_group or f"{generated_at[:10]}-{feed_key}-release-snapshot"
    release_plan = build_release_unblock_plan(
        target_commit=target_commit,
        actor=actor,
    )
    readiness = ai_visibility_live_readiness(
        feed_keys=[feed_key],
        run_group=safe_run_group,
    ).model_dump(mode="json")
    gcloud = {
        "staging": _gcloud_project_check(STAGING_PROJECT_ID),
        "production": _gcloud_project_check(PRODUCTION_PROJECT_ID),
    }
    external_probe_keys = {
        platform: {
            "env_key": env_key,
            "configured": _api_key_configured(platform),
        }
        for platform, env_key in API_ENV_KEYS.items()
    }
    blockers = _blockers(
        release_plan=release_plan,
        readiness=readiness,
        gcloud=gcloud,
        external_probe_keys=external_probe_keys,
    )
    return {
        "module_key": "ai_visibility",
        "snapshot_type": "release_blocker",
        "generated_at": generated_at,
        "feed_key": feed_key,
        "run_group": safe_run_group,
        "target_commit_sha": release_plan["target_commit_sha"],
        "official_homepage": release_plan["official_homepage"],
        "status": "blocked" if blockers else "ready_for_release_runner",
        "release_plan_status": release_plan["status"],
        "deploy_readiness_status": release_plan["deploy_readiness_status"],
        "confirmed_facts": release_plan.get("confirmed_facts", []),
        "deployment_gaps": release_plan.get("deployment_gaps", []),
        "pending_source_prs": release_plan.get("pending_source_prs", []),
        "pending_publication_gaps": release_plan.get(
            "pending_publication_gaps", []
        ),
        "verified_publication_surfaces": release_plan.get(
            "verified_publication_surfaces", []
        ),
        "live_readiness": {
            "status": readiness["status"],
            "ready_count": readiness["ready_count"],
            "blocked_count": readiness["blocked_count"],
            "items": readiness["items"],
        },
        "gcloud": gcloud,
        "external_probe_keys": external_probe_keys,
        "blockers": blockers,
        "next_actions": _next_actions(blockers),
    }


def _gcloud_project_check(
    project_id: str,
) -> dict[str, Any]:  # pragma: no cover - gcloud adapter
    command = [
        "gcloud",
        "projects",
        "describe",
        project_id,
        "--format=value(projectId)",
    ]
    try:
        completed = subprocess.run(  # nosec B603
            command,
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
        )
    except FileNotFoundError:
        return {
            "project_id": project_id,
            "ok": False,
            "status": "gcloud_missing",
            "summary": "gcloud CLI is not installed or not on PATH.",
        }
    except subprocess.TimeoutExpired:
        return {
            "project_id": project_id,
            "ok": False,
            "status": "timeout",
            "summary": "gcloud project check timed out.",
        }
    output = (completed.stdout or completed.stderr or "").strip()
    return {
        "project_id": project_id,
        "ok": completed.returncode == 0,
        "status": "ok" if completed.returncode == 0 else "failed",
        "summary": _bounded(output),
    }


def _blockers(
    *,
    release_plan: dict[str, Any],
    readiness: dict[str, Any],
    gcloud: dict[str, dict[str, Any]],
    external_probe_keys: dict[str, dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    blockers.extend(release_plan.get("known_blockers", []))
    for item in readiness.get("items", []):
        blockers.extend(item.get("missing_facts", []))
    for label, result in gcloud.items():
        if not result["ok"]:
            blockers.append(f"{label} GCloud project check failed: {result['summary']}")
    for platform, result in external_probe_keys.items():
        if not result["configured"]:
            blockers.append(
                f"{platform} external probe key missing: {result['env_key']}."
            )
    return unique_strings(blockers)


def _api_key_configured(platform: str) -> bool:
    return any(
        os.environ.get(env_key, "").strip()
        for env_key in API_ENV_KEY_ALIASES.get(platform, (API_ENV_KEYS[platform],))
    )


def _next_actions(blockers: list[str]) -> list[str]:
    if not blockers:
        return ["Run external answer-engine probes and compare citation results."]
    return [
        "Run gcloud auth login if GCloud checks are blocked.",
        "Rerun live readiness and external GPT/Claude/Grok/Gemini probes after feed validation passes.",
    ]


def _bounded(value: str, limit: int = 500) -> str:
    clean = " ".join(value.split())
    return clean[:limit]
