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
) -> str:
    lines = [
        f"# Requirement #{requirement_id}",
        "",
        requirement_title.strip() or f"Requirement #{requirement_id}",
        "",
        f"- Head branch: `{branch_name}`",
        f"- Base branch: `{base_branch}`",
    ]
    if latest_commit_sha:
        lines.append(f"- Latest commit: `{latest_commit_sha[:12]}`")
    if compare_url:
        lines.append(f"- Compare: {compare_url}")
    summary = str(summary_markdown or "").strip()
    if summary:
        lines.extend(["", "## Review Bundle", summary])
    if checklist:
        lines.extend(["", "## Promotion Checklist"])
        for item in checklist:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("key") or "check").strip()
            status = str(item.get("status") or "pending").strip()
            detail = str(item.get("detail") or "").strip()
            suffix = f" — {detail}" if detail else ""
            lines.append(f"- [{status}] {label}{suffix}")
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
    body = _pr_body(
        requirement_id=requirement_id,
        requirement_title=requirement_title,
        summary_markdown=review_surface_summary,
        compare_url=compare_url,
        checklist=promotion_checklist,
        branch_name=branch_name,
        base_branch=base_branch,
        latest_commit_sha=latest_commit_sha,
    )

    blockers: list[str] = []
    sync_action = "noop"
    pr_payload = _load_existing_pr(repo_slug, branch_name)
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
        "draft": pr_status == "draft",
        "blockers": blockers,
    }

