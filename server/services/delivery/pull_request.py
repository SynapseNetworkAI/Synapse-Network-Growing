from __future__ import annotations

"""Deterministic GitHub PR sync for requirement delivery branches."""

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any

from server import config


def _github_https_remote(remote_url: str | None) -> str | None:
    value = str(remote_url or "").strip()
    if not value:
        return None
    if value.startswith("git@github.com:"):
        path = value.split(":", 1)[1]
        if path.endswith(".git"):
            path = path[:-4]
        return f"https://github.com/{path}"
    match = re.match(r"https?://github\.com/(?P<path>.+?)(?:\.git)?/?$", value)
    if match:
        return f"https://github.com/{match.group('path')}"
    return None


def _github_repo_slug(remote_url: str | None) -> str | None:
    https_remote = _github_https_remote(remote_url)
    if not https_remote:
        return None
    path = https_remote.removeprefix("https://github.com/").strip("/")
    return path or None


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gh_env() -> dict[str, str]:
    env = os.environ.copy()
    token = (
        config.GH_TOKEN.strip()
        or config.GITHUB_TOKEN.strip()
        or config.COPILOT_GITHUB_TOKEN.strip()
    )
    if token:
        env.setdefault("GH_TOKEN", token)
        env.setdefault("GITHUB_TOKEN", token)
    return env


def _run_gh(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    gh_bin = shutil.which("gh") or "gh"
    completed = subprocess.run(
        [gh_bin, *args],
        capture_output=True,
        text=True,
        timeout=max(1, config.DELIVERY_PR_TIMEOUT_SECONDS),
        env=_gh_env(),
    )
    if check and completed.returncode != 0:
        command = " ".join(["gh", *args])
        stderr = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"{command} failed: {stderr or 'unknown gh error'}")
    return completed


def _pr_status_from_payload(payload: dict[str, Any]) -> str:
    state = str(payload.get("state") or "").strip().upper()
    is_draft = bool(payload.get("isDraft"))
    if state == "MERGED":
        return "merged"
    if state == "CLOSED":
        return "closed"
    return "draft" if is_draft else "ready_for_review"


def _pr_body(
    *,
    requirement_id: int,
    requirement_title: str,
    summary_markdown: str,
    compare_url: str | None,
    checklist: list[dict[str, Any]] | None,
    branch_name: str,
    base_branch: str,
    latest_commit_sha: str | None,
    goal_key: str | None = None,
    vcs_payload: dict[str, Any] | None = None,
) -> str:
    repositories = [item for item in (vcs_payload or {}).get("repositories") or [] if isinstance(item, dict)]
    human_commits_detected = bool((vcs_payload or {}).get("human_commits_detected")) or any(
        bool(item.get("human_commits_detected")) for item in repositories
    )
    rebase_status = str((vcs_payload or {}).get("rebase_status") or "").strip()
    delivery_status = str((vcs_payload or {}).get("status") or "").strip()
    summary = str(summary_markdown or "").strip()
    lines = [
        f"# Requirement #{requirement_id}",
        "",
        requirement_title.strip() or f"Requirement #{requirement_id}",
        "",
        "> Agent generated this PR. Human merge required.",
        "",
        "## What changed",
        summary or "Agent prepared a scoped implementation for this requirement. Review the diff and evidence before merging.",
        "",
        "## Why it is safe to review",
        f"- Head branch: `{branch_name}`",
        f"- Base branch: `{base_branch}`",
        f"- Delivery sync: `{delivery_status or 'unknown'}`",
    ]
    if goal_key:
        lines.append(f"- Goal key: `{goal_key}`")
    if latest_commit_sha:
        lines.append(f"- Latest commit: `{latest_commit_sha[:12]}`")
    if compare_url:
        lines.append(f"- Compare: {compare_url}")
    if human_commits_detected:
        lines.append(f"- Human commits detected on branch and rebase status is `{rebase_status or 'unknown'}`.")

    lines.extend(
        [
            "",
            "## Human merge checklist",
            "- [ ] Review every changed file and confirm the business intent is satisfied.",
            "- [ ] Confirm required checks and evidence artifacts are green.",
            "- [ ] Merge only after human review; this workflow never auto-merges.",
        ]
    )

    lines.extend(["", "<details>", "<summary>Acceptance steps and promotion checklist</summary>", ""])
    if checklist:
        for item in checklist:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("key") or "check").strip()
            status = str(item.get("status") or "pending").strip()
            detail = str(item.get("detail") or "").strip()
            suffix = f" — {detail}" if detail else ""
            lines.append(f"- [{status}] {label}{suffix}")
    else:
        lines.append("- No structured checklist was supplied in the PR sync payload.")
    lines.extend(["", "</details>"])

    lines.extend(["", "<details>", "<summary>Delivery / VCS evidence</summary>", ""])
    lines.append(f"- Delivery status: `{delivery_status or 'unknown'}`")
    lines.append(f"- Rebase attempted: `{bool((vcs_payload or {}).get('rebase_attempted'))}`")
    lines.append(f"- Rebase status: `{rebase_status or 'not_reported'}`")
    lines.append(f"- Push mode: `{(vcs_payload or {}).get('push_mode') or 'not_reported'}`")
    lines.append(f"- Human commits detected: `{human_commits_detected}`")
    for index, repo in enumerate(repositories, start=1):
        lines.append(
            f"- Repo {index}: `{repo.get('repo_path') or 'unknown'}` "
            f"branch `{repo.get('branch_name') or branch_name}` "
            f"remote `{repo.get('remote_sha') or repo.get('remote_branch_before_sha') or 'not_reported'}`"
        )
    lines.extend(["", "</details>"])

    lines.extend(["", "<details>", "<summary>Checks projection bundle</summary>", ""])
    for key in ("architecture_contracts", "tests", "coverage", "doc_sync", "delivery_vcs"):
        status = "passed" if key == "delivery_vcs" and delivery_status == "delivered" else "not_reported"
        lines.append(f"- `{key}`: `{status}`")
    lines.extend(["", "</details>"])
    return "\n".join(lines)


def _load_existing_pr(repo_slug: str, branch_name: str) -> dict[str, Any] | None:
    completed = _run_gh(
        "pr",
        "view",
        branch_name,
        "--repo",
        repo_slug,
        "--json",
        "number,url,isDraft,state,headRefName,baseRefName,title",
        check=False,
    )
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def query_review_pr_status(*, pr_ref: str, repo_slug: str | None = None) -> dict[str, Any]:
    """Read one GitHub PR status through the existing gh/token path.

    The return value is deliberately classified so callers can distinguish a
    business-terminal missing PR from transient network/API failures.
    """

    args = [
        "pr",
        "view",
        str(pr_ref or "").strip(),
        "--json",
        "number,url,isDraft,state,headRefName,baseRefName,title,mergedAt,closedAt,mergeCommit",
    ]
    if str(repo_slug or "").strip():
        args.extend(["--repo", str(repo_slug).strip()])
    completed = _run_gh(*args, check=False)
    stderr = (completed.stderr or completed.stdout or "").strip()
    lowered = stderr.lower()
    if completed.returncode != 0:
        if (
            "not found" in lowered
            or "no pull requests found" in lowered
            or "http 404" in lowered
            or "could not resolve to a pullrequest" in lowered
        ):
            return {
                "result": "not_found",
                "error_excerpt": stderr[:1000],
                "pr_ref": pr_ref,
                "repo_slug": repo_slug,
            }
        if any(marker in lowered for marker in ("authentication", "not logged in", "permission", "http 401", "http 403")):
            return {
                "result": "auth_error",
                "error_excerpt": stderr[:1000],
                "pr_ref": pr_ref,
                "repo_slug": repo_slug,
            }
        return {
            "result": "transient_error",
            "error_excerpt": stderr[:1000],
            "pr_ref": pr_ref,
            "repo_slug": repo_slug,
        }
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        return {
            "result": "transient_error",
            "error_excerpt": f"Failed to parse gh pr view JSON: {exc}",
            "pr_ref": pr_ref,
            "repo_slug": repo_slug,
        }
    if not isinstance(payload, dict) or not payload:
        return {
            "result": "transient_error",
            "error_excerpt": "gh pr view returned an empty payload",
            "pr_ref": pr_ref,
            "repo_slug": repo_slug,
        }
    return {
        "result": "ok",
        "payload": payload,
        "pr_ref": pr_ref,
        "repo_slug": repo_slug,
    }


def sync_requirement_review_pr(
    *,
    requirement_id: int,
    requirement_title: str,
    branch_name: str,
    base_branch: str,
    compare_url: str | None,
    latest_commit_sha: str | None,
    latest_remote_sha: str | None,
    last_pushed_at: str | None,
    review_surface_summary: str,
    promotion_checklist: list[dict[str, Any]] | None = None,
    vcs_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repositories = list((vcs_payload or {}).get("repositories") or [])
    remote_url = None
    for item in repositories:
        if not isinstance(item, dict):
            continue
        remote_url = str(item.get("remote_url") or "").strip() or None
        if remote_url:
            break
    repo_slug = _github_repo_slug(remote_url)
    if not repo_slug:
        return {
            "status": "missing",
            "pr_status": "missing",
            "branch_name": branch_name,
            "base_branch": base_branch,
            "compare_url": compare_url,
            "latest_commit_sha": latest_commit_sha,
            "latest_remote_sha": latest_remote_sha,
            "last_pushed_at": last_pushed_at,
            "review_bundle_generated_at": _utcnow_iso(),
            "sync_action": "skipped",
            "blockers": ["delivery remote is not a supported GitHub repository"],
        }

    title = f"ops(req-{requirement_id}): {requirement_title.strip() or f'requirement-{requirement_id}'}"[:120]
    human_commits_detected = bool((vcs_payload or {}).get("human_commits_detected")) or any(
        bool(item.get("human_commits_detected")) for item in repositories if isinstance(item, dict)
    )
    body = _pr_body(
        requirement_id=requirement_id,
        requirement_title=requirement_title,
        summary_markdown=review_surface_summary,
        compare_url=compare_url,
        checklist=promotion_checklist,
        branch_name=branch_name,
        base_branch=base_branch,
        latest_commit_sha=latest_commit_sha,
        goal_key=str((vcs_payload or {}).get("goal_key") or "").strip() or None,
        vcs_payload=vcs_payload,
    )

    blockers: list[str] = []
    sync_action = "noop"
    pr_payload = _load_existing_pr(repo_slug, branch_name)
    existing_pr_url = str((pr_payload or {}).get("url") or "").strip() or None
    try:
        if pr_payload is None:
            create = _run_gh(
                "pr",
                "create",
                "--repo",
                repo_slug,
                "--base",
                base_branch,
                "--head",
                branch_name,
                "--title",
                title,
                "--body",
                body,
                "--draft",
            )
            sync_action = "created"
            pr_payload = _load_existing_pr(repo_slug, branch_name)
            if pr_payload is None:
                url = (create.stdout or "").strip().splitlines()
                guessed_url = url[-1].strip() if url else None
                pr_payload = {"url": guessed_url, "title": title, "state": "OPEN", "isDraft": True}
        else:
            _run_gh(
                "pr",
                "edit",
                str(pr_payload.get("number")),
                "--repo",
                repo_slug,
                "--title",
                title,
                "--body",
                body,
            )
            sync_action = "updated"
            pr_payload = _load_existing_pr(repo_slug, branch_name) or pr_payload
    except Exception as exc:  # noqa: BLE001
        blockers.append(str(exc))

    normalized = pr_payload if isinstance(pr_payload, dict) else {}
    pr_status = _pr_status_from_payload(normalized) if normalized else "missing"
    if blockers:
        pr_status = "missing"
    return {
        "status": "synced" if not blockers and normalized else "blocked" if blockers else "missing",
        "pr_status": pr_status,
        "pr_number": int(normalized.get("number") or 0) or None,
        "pr_url": str(normalized.get("url") or "").strip() or None,
        "pr_title": str(normalized.get("title") or title).strip() or title,
        "branch_name": branch_name,
        "head_branch": str(normalized.get("headRefName") or branch_name).strip() or branch_name,
        "base_branch": str(normalized.get("baseRefName") or base_branch).strip() or base_branch,
        "repo_slug": repo_slug,
        "remote_url": remote_url,
        "compare_url": compare_url,
        "latest_commit_sha": latest_commit_sha,
        "latest_remote_sha": latest_remote_sha,
        "last_pushed_at": last_pushed_at,
        "review_bundle_generated_at": _utcnow_iso(),
        "sync_action": sync_action,
        "existing_pr_url": existing_pr_url,
        "body_sections_collapsed": True,
        "review_bundle_summary": "Reviewer-first PR body generated with folded acceptance, delivery, and checks evidence.",
        "checks_projection_ready": True,
        "checks_projection": {
            "architecture_contracts": "not_reported",
            "tests": "not_reported",
            "coverage": "not_reported",
            "doc_sync": "not_reported",
            "delivery_vcs": "passed" if str((vcs_payload or {}).get("status") or "") == "delivered" else "blocked",
        },
        "human_commits_detected": human_commits_detected,
        "draft": pr_status == "draft",
        "blockers": blockers,
    }
