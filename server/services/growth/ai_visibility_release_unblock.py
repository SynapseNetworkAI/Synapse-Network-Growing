"""Operator command plan for unblocking an AI visibility release train."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from server.services.growth.ai_visibility_plan import CANONICAL_HOMEPAGE

DEFAULT_TARGET_COMMIT = "6a1571c136c564e8c8a6202ce6bf9c4c5f491846"
DEFAULT_ACTOR = "codex/ai-visibility-release-unblock"
PROJECT_KEY = "synapse-network"
SERVICES = ("docs-front", "user-front")
STAGING_PROJECT_ID = "fabled-archive-494108-k5"
PRODUCTION_PROJECT_ID = "synapse-network-prod"
REGION = "us-central1"
SOURCE_PR = {
    "number": 214,
    "url": "https://github.com/SynapseNetworkAI/Synapse-Network/pull/214",
    "state": "MERGED",
    "head_ref": "codex/ai-visibility-synapse-mcp-collision-feed",
    "base_ref": "main",
    "merged_at": "2026-06-05T19:09:16Z",
    "merge_commit": DEFAULT_TARGET_COMMIT,
}
SOURCE_PRS = [
    {
        "number": 203,
        "url": "https://github.com/SynapseNetworkAI/Synapse-Network/pull/203",
        "state": "MERGED",
        "head_ref": "codex/mcp-paid-api-docs-feed",
        "base_ref": "main",
        "merged_at": "2026-06-04T21:57:02Z",
        "merge_commit": "04c6cfd4477f86569c83322a1119580dcf01091e",
        "purpose": "Add MCP paid API calls visibility docs and www llms feed.",
    },
    {
        "number": 204,
        "url": "https://github.com/SynapseNetworkAI/Synapse-Network/pull/204",
        "state": "MERGED",
        "head_ref": "codex/ai-visibility-docs-llms-endpoint",
        "base_ref": "main",
        "merged_at": "2026-06-05T00:54:23Z",
        "merge_commit": "d8b5371e11fea2d962dcc656b9b8d08d0c1379d9",
        "purpose": "Expose the MCP paid API docs URL and Remote MCP endpoint in docs-front llms.txt.",
    },
    {
        "number": 212,
        "url": "https://github.com/SynapseNetworkAI/Synapse-Network/pull/212",
        "state": "MERGED",
        "head_ref": "codex/ai-visibility-mcp-competitor-feed",
        "base_ref": "main",
        "merged_at": "2026-06-05T18:57:18Z",
        "merge_commit": "7657d220f672dd7e94e2ed15085201fa7e5e5d64",
        "purpose": "Add the observed paid MCP competitor set to public answer-engine feeds.",
    },
    {
        "number": 213,
        "url": "https://github.com/SynapseNetworkAI/Synapse-Network/pull/213",
        "state": "MERGED",
        "head_ref": "codex/ai-visibility-protodex-disambiguation-feed",
        "base_ref": "main",
        "merged_at": "2026-06-05T19:05:54Z",
        "merge_commit": "cc3560a8fd99bf128d3dd5147c321761c8ccd1f5",
        "purpose": "Add Protodex directory visibility and Synapse-looking MCP disambiguation feed.",
    },
    {
        "number": 214,
        "url": "https://github.com/SynapseNetworkAI/Synapse-Network/pull/214",
        "state": "MERGED",
        "head_ref": "codex/ai-visibility-synapse-mcp-collision-feed",
        "base_ref": "main",
        "merged_at": "2026-06-05T19:09:16Z",
        "merge_commit": DEFAULT_TARGET_COMMIT,
        "purpose": "Add near-name Synapse/Synap MCP collision handling for current search results.",
    },
]
PENDING_SOURCE_PRS = [
    {
        "number": 215,
        "url": "https://github.com/SynapseNetworkAI/Synapse-Network/pull/215",
        "state": "OPEN",
        "head_ref": "codex/add-mcp-search-landing-pages",
        "base_ref": "main",
        "head_commit": "794a416bd85a9042e8e652eaf02f0ebf2552e85d",
        "purpose": (
            "Add MCP search landing pages, the Synapse vs paid MCP comparison "
            "page, and Synapse Protocol disambiguation feed assets."
        ),
    },
]
PENDING_PUBLICATION_GAPS = [
    {
        "surface": "docs",
        "url": "https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp",
        "current_status": 404,
        "expected_after_merge": 200,
        "source_pr": 215,
        "next_action": "Merge PR #215, deploy docs-front, then rerun live readiness.",
    },
    {
        "surface": "www",
        "url": "https://www.synapse-network.ai/mcp-server-for-paid-api-calls",
        "current_status": 404,
        "expected_after_merge": 200,
        "source_pr": 215,
        "next_action": "Merge PR #215, deploy user-front, then rerun live readiness.",
    },
    {
        "surface": "www",
        "url": "https://www.synapse-network.ai/chatgpt-mcp-app-api-payments",
        "current_status": 404,
        "expected_after_merge": 200,
        "source_pr": 215,
        "next_action": "Merge PR #215, deploy user-front, then rerun live readiness.",
    },
]
DEPLOYMENT_GAP_BASES = [
    {
        "service_key": "docs-front",
        "staging_commit": "7657d220f672dd7e94e2ed15085201fa7e5e5d64",
        "production_commit": "7657d220f672dd7e94e2ed15085201fa7e5e5d64",
        "latest_staging_record_id": 244,
        "latest_production_record_id": 246,
        "status": "staging_and_production_behind_target",
    },
    {
        "service_key": "user-front",
        "staging_commit": "7657d220f672dd7e94e2ed15085201fa7e5e5d64",
        "production_commit": "",
        "latest_staging_record_id": 245,
        "latest_production_record_id": 247,
        "status": "production_failed_for_previous_target",
    },
]
PREDEPLOY_EVIDENCE_PATH = (
    "docs/archive/evidence/growth/ai-visibility/"
    "2026-06-05-synapse-target-branch-predeploy-readiness.json"
)


def build_release_unblock_plan(*, target_commit: str, actor: str) -> dict[str, Any]:
    target_commit = _clean(target_commit) or DEFAULT_TARGET_COMMIT
    actor = _clean(actor) or DEFAULT_ACTOR
    predeploy_evidence = _load_predeploy_evidence()
    deploy_readiness = _deploy_readiness_status(predeploy_evidence, target_commit)
    return {
        "module_key": "ai_visibility",
        "feed_key": "mcp_paid_api_discovery",
        "status": (
            "blocked_until_gcloud_auth"
            if deploy_readiness == "ready_for_release_runner_after_gcloud_auth"
            else deploy_readiness
        ),
        "generated_at": datetime.now(UTC).isoformat(),
        "official_homepage": CANONICAL_HOMEPAGE,
        "project_key": PROJECT_KEY,
        "services": list(SERVICES),
        "branch_name": "main",
        "target_commit_sha": target_commit,
        "actor": actor,
        "source_pr": SOURCE_PR,
        "source_prs": SOURCE_PRS,
        "pending_source_prs": PENDING_SOURCE_PRS,
        "predeploy_evidence": predeploy_evidence,
        "deploy_readiness_status": deploy_readiness,
        "deployment_gaps": _deployment_gaps(target_commit),
        "pending_publication_gaps": PENDING_PUBLICATION_GAPS,
        "confirmed_facts": _confirmed_facts(target_commit),
        "hard_boundaries": [
            "Do not run gcloud run deploy directly.",
            "Do not manually mark a deployment successful.",
            "Production must promote the successful staging digest for the same commit.",
            "Do not paste OPS_AGENT_DEPLOY_API_TOKEN, cookies, GCP credentials, or API keys into evidence.",
        ],
        "known_blockers": _known_blockers(
            deploy_readiness, predeploy_evidence, target_commit
        ),
        "environment_defaults": {
            "ops_base_url": "http://localhost:9700",
            "staging_gcp_project": STAGING_PROJECT_ID,
            "production_gcp_project": PRODUCTION_PROJECT_ID,
            "region": REGION,
            "target_repo_worktree": "/private/tmp/synapse-ai-visibility-publish",
        },
        "command_groups": [
            _gcloud_preflight_group(target_commit),
            _growing_preflight_group(),
            _task_status_group(),
            _staging_group("docs-front", actor),
            _staging_group("user-front", actor),
            _staging_validation_group(),
            _production_group("docs-front", actor),
            _production_group("user-front", actor),
            _production_validation_group(),
            _answer_engine_probe_group(),
        ],
        "success_criteria": [
            "docs-front and user-front staging tasks complete with DeploymentRecord.status=succeeded.",
            "Production tasks promote staging image digest for target_commit_sha.",
            "https://docs.synapse-network.ai/mcp/paid-api-calls returns 200 and includes discover_services, invoke_and_pay, and get_receipt.",
            "https://www.synapse-network.ai/llms.txt includes MCP Server for Paid API Calls and https://mcp.synapse-network.ai/mcp.",
            "https://mcp.synapse-network.ai/readyz returns 200 and unauthenticated /mcp returns 401.",
            "Only after production validation passes, run unchanged ChatGPT, Claude, and Grok probes and record evidence.",
        ],
}


def _gcloud_preflight_group(target_commit: str) -> dict[str, Any]:
    return {
        "key": "gcloud_auth_and_target_commit_preflight",
        "purpose": "Restore non-interactive GCloud access and confirm the target main commit.",
        "commands": [
            "gcloud auth login",
            f"gcloud projects describe {STAGING_PROJECT_ID} --format='value(projectId)'",
            f"gcloud projects describe {PRODUCTION_PROJECT_ID} --format='value(projectId)'",
            "git -C /private/tmp/synapse-ai-visibility-publish fetch origin main",
            "git -C /private/tmp/synapse-ai-visibility-publish rev-parse origin/main",
            f"test \"$(git -C /private/tmp/synapse-ai-visibility-publish rev-parse origin/main)\" = \"{target_commit}\"",
            "node /private/tmp/synapse-ai-visibility-publish/scripts/ci/ai_visibility_assets_check.mjs",
            "node /private/tmp/synapse-ai-visibility-publish/scripts/ci/seo_public_assets_check.mjs",
        ],
    }


def _growing_preflight_group() -> dict[str, Any]:
    return {
        "key": "growing_release_api_preflight",
        "purpose": "Ensure Growing API is reachable and the deploy token exists before creating release tasks.",
        "commands": [
            "export OPS_BASE_URL=${OPS_BASE_URL:-http://localhost:9700}",
            "test -n \"$OPS_AGENT_DEPLOY_API_TOKEN\"",
            "curl -fsS \"$OPS_BASE_URL/api/health\" || curl -fsS \"$OPS_BASE_URL/api/releases/tasks?limit=1\"",
        ],
    }


def _task_status_group() -> dict[str, Any]:
    return {
        "key": "inspect_existing_release_tasks",
        "purpose": "Check existing tasks before creating fresh attempts for the same services.",
        "commands": [
            "curl -fsS \"$OPS_BASE_URL/api/releases/tasks?project_key=synapse-network&service_key=docs-front\" | python -m json.tool",
            "curl -fsS \"$OPS_BASE_URL/api/releases/tasks?project_key=synapse-network&service_key=user-front\" | python -m json.tool",
        ],
        "notes": [
            "If an older task is stuck in deploying, reset it only through the release-task reset API/UI with confirmation phrase RESET_LOCAL_DEPLOY.",
            "If an older task failed from stale GCloud auth, create a fresh task after auth is restored.",
        ],
    }


def _staging_group(service_key: str, actor: str) -> dict[str, Any]:
    task_var = _var(service_key, "STAGING_TASK_ID")
    record_var = _var(service_key, "STAGING_DEPLOYMENT_RECORD_ID")
    return {
        "key": f"create_and_run_{service_key}_staging",
        "service_key": service_key,
        "environment": "staging",
        "purpose": f"Create a {service_key} staging task from main and run the local deploy worker.",
        "commands": [
            _create_task_command(service_key, "staging", actor),
            f"export {task_var}=<task_id_from_create_response>",
            _request_staging_command(task_var, actor),
            f"export {record_var}=<deployment_record_id_from_deploy_response>",
            f"PYTHONPATH=. .venv/bin/python scripts/local/run_deploy_worker.py --once --deployment-record-id ${record_var}",
            f"curl -fsS \"$OPS_BASE_URL/api/releases/tasks/${task_var}\" | python -m json.tool",
        ],
    }


def _production_group(service_key: str, actor: str) -> dict[str, Any]:
    task_var = _var(service_key, "PROD_TASK_ID")
    record_var = _var(service_key, "PROD_DEPLOYMENT_RECORD_ID")
    return {
        "key": f"create_and_run_{service_key}_production",
        "service_key": service_key,
        "environment": "production",
        "purpose": f"Promote the successful {service_key} staging digest to production.",
        "commands": [
            _create_task_command(service_key, "production", actor),
            f"export {task_var}=<task_id_from_create_response>",
            _request_production_command(task_var, actor),
            f"export {record_var}=<deployment_record_id_from_deploy_response>",
            f"PYTHONPATH=. .venv/bin/python scripts/local/run_deploy_worker.py --once --deployment-record-id ${record_var}",
            f"curl -fsS \"$OPS_BASE_URL/api/releases/tasks/${task_var}\" | python -m json.tool",
        ],
        "notes": [
            "If the production deploy response reports staging_digest_missing, inspect the matching staging task metadata before retrying.",
        ],
    }


def _staging_validation_group() -> dict[str, Any]:
    return {
        "key": "staging_validation",
        "purpose": "Verify staging feed content before production promotion.",
        "commands": [
            "curl -fsS https://docs-staging.synapse-network.ai/mcp/paid-api-calls | grep -E 'MCP Server for Paid API Calls|discover_services|invoke_and_pay|get_receipt'",
            "curl -fsS https://staging.synapse-network.ai/llms.txt | grep -E 'MCP Server for Paid API Calls|https://mcp.synapse-network.ai/mcp'",
        ],
    }


def _production_validation_group() -> dict[str, Any]:
    return {
        "key": "production_validation",
        "purpose": "Verify the public feed that GPT, Claude, and Grok can crawl.",
        "commands": [
            f"curl -fsS {CANONICAL_HOMEPAGE}",
            "curl -fsS https://docs.synapse-network.ai/mcp/paid-api-calls | grep -E 'MCP Server for Paid API Calls|discover_services|invoke_and_pay|get_receipt'",
            "curl -fsS https://www.synapse-network.ai/llms.txt | grep -E 'MCP Server for Paid API Calls|https://mcp.synapse-network.ai/mcp'",
            "curl -fsS https://mcp.synapse-network.ai/readyz",
            "test \"$(curl -o /tmp/synapse-mcp-unauth.out -sS -w '%{http_code}' -X POST https://mcp.synapse-network.ai/mcp)\" = \"401\"",
            "python scripts/growth/run_ai_visibility_feed_validation.py --feed-key mcp_paid_api_discovery --run-group 2026-06-05-after-prod --output docs/archive/evidence/growth/ai-visibility/2026-06-05-after-prod-feed-validation.jsonl",
            "python scripts/growth/summarize_ai_visibility_cycle.py docs/archive/evidence/growth/ai-visibility/2026-06-05-after-prod-feed-validation.jsonl --output docs/archive/evidence/growth/ai-visibility/2026-06-05-after-prod-cycle-summary.json",
        ],
    }


def _answer_engine_probe_group() -> dict[str, Any]:
    return {
        "key": "post_publish_answer_engine_probe",
        "purpose": "Run external probes only after production feed validation has passed.",
        "commands": [
            "python scripts/growth/generate_ai_visibility_probe_template.py --feed-key mcp_paid_api_discovery --run-group 2026-06-05-after-prod --mode after-feed --output docs/archive/evidence/growth/ai-visibility/2026-06-05-after-prod-external-probes.jsonl",
            "python scripts/growth/run_ai_visibility_api_probe.py --feed-key mcp_paid_api_discovery --run-group 2026-06-05-after-prod --platforms chatgpt,claude,grok",
            "python scripts/growth/run_ai_visibility_api_probe.py --feed-key mcp_paid_api_discovery --run-group 2026-06-05-after-prod --platforms chatgpt,claude,grok --execute",
            "python scripts/growth/record_ai_visibility_probe.py docs/archive/evidence/growth/ai-visibility/2026-06-05-after-prod-external-probes.jsonl --apply",
        ],
        "notes": [
            "The readiness command is safe; the --execute command requires provider API keys in the local environment.",
            "Manual ChatGPT/Claude/Grok screenshots are acceptable evidence when API probing is unavailable.",
        ],
    }


def _known_blockers(
    deploy_readiness: str, predeploy_evidence: dict[str, Any], target_commit: str
) -> list[str]:
    blockers = [
        "GCloud auth fails non-interactively until a human runs gcloud auth login.",
    ]
    for item in PENDING_SOURCE_PRS:
        blockers.append(
            (
                f"Synapse-Network PR #{item['number']} is {item['state']}; "
                "merge and deploy it before validating the new MCP comparison "
                "and www landing pages."
            )
        )
    if deploy_readiness == "blocked_until_target_commit_matches":
        evidence_commit = _clean(str(predeploy_evidence.get("commit") or ""))
        blockers.insert(
            1,
            (
                f"Target commit {target_commit[:12]} does not match current "
                f"predeploy evidence commit {evidence_commit[:12] or 'missing'}."
            ),
        )
    return blockers


def _confirmed_facts(target_commit: str) -> list[str]:
    latest_pr = SOURCE_PR.get("number")
    return [
        f"Official homepage canonical is {CANONICAL_HOMEPAGE}.",
        f"Synapse-Network main is pinned to merged PR #{latest_pr} commit {target_commit}.",
        "Remote MCP endpoint is https://mcp.synapse-network.ai/mcp; live readiness expects /readyz=200 and unauthenticated /mcp=401.",
        "Growing release runner remains the deployment path; direct gcloud run deploy is out of bounds.",
    ]


def _deployment_gaps(target_commit: str) -> list[dict[str, Any]]:
    target_short = target_commit[:12]
    gaps: list[dict[str, Any]] = []
    for base in DEPLOYMENT_GAP_BASES:
        service_key = str(base["service_key"])
        next_action = (
            f"Re-run {service_key} staging for {target_short}, then promote production."
        )
        if base["status"] == "production_failed_for_previous_target":
            next_action = (
                f"Re-run {service_key} staging for {target_short}; the previous "
                "production promotion failed and must not be reused."
            )
        gaps.append({**base, "target_commit": target_commit, "next_action": next_action})
    return gaps


def _create_task_command(service_key: str, environment: str, actor: str) -> str:
    body = {
        "project_key": PROJECT_KEY,
        "service_key": service_key,
        "branch_name": "main",
        "environment": environment,
        "source_type": "manual",
        "actor": actor,
        "note": "AI visibility MCP paid API feed publication",
    }
    return (
        "curl -sS -X POST \"$OPS_BASE_URL/api/releases/tasks\" "
        "-H \"Content-Type: application/json\" "
        "-H \"X-Growing-Agent-Deploy-Token: $OPS_AGENT_DEPLOY_API_TOKEN\" "
        f"-d '{json.dumps(body, separators=(',', ':'))}'"
    )


def _request_staging_command(task_var: str, actor: str) -> str:
    body = {"actor": actor, "note": "AI visibility staging via local deploy runner"}
    return (
        f"curl -sS -X POST \"$OPS_BASE_URL/api/releases/tasks/${task_var}/deploy-staging\" "
        "-H \"Content-Type: application/json\" "
        "-H \"X-Growing-Agent-Deploy-Token: $OPS_AGENT_DEPLOY_API_TOKEN\" "
        f"-d '{json.dumps(body, separators=(',', ':'))}'"
    )


def _request_production_command(task_var: str, actor: str) -> str:
    body = {
        "actor": actor,
        "confirm_phrase": "YES",
        "note": "Promote successful AI visibility staging digest",
    }
    return (
        f"curl -sS -X POST \"$OPS_BASE_URL/api/releases/tasks/${task_var}/deploy\" "
        "-H \"Content-Type: application/json\" "
        "-H \"X-Growing-Agent-Deploy-Token: $OPS_AGENT_DEPLOY_API_TOKEN\" "
        f"-d '{json.dumps(body, separators=(',', ':'))}'"
    )


def _var(service_key: str, suffix: str) -> str:
    return f"{service_key.replace('-', '_').upper()}_{suffix}"


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def _load_predeploy_evidence() -> dict[str, Any]:
    evidence_path = Path(__file__).resolve().parents[3] / PREDEPLOY_EVIDENCE_PATH
    if not evidence_path.exists():
        return {
            "status": "missing",
            "path": PREDEPLOY_EVIDENCE_PATH,
            "summary": "Target-branch predeploy evidence has not been generated.",
        }
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "status": "invalid_json",
            "path": PREDEPLOY_EVIDENCE_PATH,
            "summary": f"Target-branch predeploy evidence JSON is invalid: {exc}",
        }
    validation = payload.get("validation") if isinstance(payload, dict) else []
    screenshots = payload.get("screenshots") if isinstance(payload, dict) else []
    return {
        "status": str(payload.get("status") or "unknown"),
        "path": PREDEPLOY_EVIDENCE_PATH,
        "target_worktree": str(payload.get("target_worktree") or ""),
        "branch": str(payload.get("branch") or ""),
        "commit": str(payload.get("commit") or ""),
        "commit_subject": str(payload.get("commit_subject") or ""),
        "validation_count": len(validation) if isinstance(validation, list) else 0,
        "validations": validation if isinstance(validation, list) else [],
        "screenshots": screenshots if isinstance(screenshots, list) else [],
    }


def _deploy_readiness_status(
    predeploy_evidence: dict[str, Any],
    target_commit: str,
) -> str:
    if SOURCE_PR.get("state") != "MERGED":
        return "blocked_until_pr_merged"
    if predeploy_evidence.get("status") != "target_branch_ready_live_prod_blocked":
        return "blocked_until_predeploy_evidence"
    if str(predeploy_evidence.get("commit") or "") != target_commit:
        return "blocked_until_target_commit_matches"
    return "ready_for_release_runner_after_gcloud_auth"
