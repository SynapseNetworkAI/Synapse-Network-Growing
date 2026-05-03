"""GitHub CLI helpers for release services."""

from __future__ import annotations

import json
import subprocess  # nosec B404
from typing import Any
from urllib.parse import quote

from server.services.delivery.pull_request import _gh_env

_NOT_FOUND_MARKERS = (
    "not found",
    "no pull requests found",
    "http 404",
    "could not resolve",
)
_AUTH_ERROR_MARKERS = (
    "authentication",
    "not logged in",
    "permission",
    "http 401",
    "http 403",
)


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def _bounded_error_excerpt(value: str, limit: int = 1000) -> str:
    cleaned = _clean(value).replace("\r", "")
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}... [Truncated]"


def _classify_gh_error(stderr: str) -> tuple[str, Any | None, str]:
    lowered = stderr.lower()
    if any(marker in lowered for marker in _NOT_FOUND_MARKERS):
        return "not_found", None, stderr or "GitHub resource was not found."
    if any(marker in lowered for marker in _AUTH_ERROR_MARKERS):
        return "auth_error", None, stderr or "GitHub authentication failed."
    return "transient_error", None, stderr or "GitHub CLI request failed."


def run_gh_json(args: list[str], *, timeout: int = 30) -> tuple[str, Any | None, str]:
    """Run gh and classify the result without raising on GitHub domain states."""

    try:
        completed = subprocess.run(  # nosec B603 B607
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=_gh_env(),
        )
    except FileNotFoundError:
        return "transient_error", None, "GitHub CLI 'gh' is required."
    except subprocess.TimeoutExpired:
        return "transient_error", None, "GitHub CLI request timed out."
    stderr = _bounded_error_excerpt(completed.stderr or completed.stdout or "", 1000)
    if completed.returncode != 0:
        return _classify_gh_error(stderr)
    try:
        return "ok", json.loads(completed.stdout or "null"), ""
    except json.JSONDecodeError as exc:
        return "transient_error", None, f"GitHub response was not valid JSON: {exc}"


def run_gh_text(args: list[str], *, timeout: int = 30) -> tuple[str, str | None, str]:
    try:
        completed = subprocess.run(  # nosec B603 B607
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=_gh_env(),
        )
    except FileNotFoundError:
        return "transient_error", None, "GitHub CLI 'gh' is required."
    except subprocess.TimeoutExpired:
        return "transient_error", None, "GitHub CLI request timed out."
    if completed.returncode != 0:
        return (
            "transient_error",
            None,
            _bounded_error_excerpt(completed.stderr or completed.stdout or "", 1000),
        )
    return "ok", completed.stdout or "", ""


def github_branch_exists(
    repo_full_name: str,
    branch_name: str,
    *,
    e2e_mode: bool,
    e2e_branch_options: list[str],
) -> tuple[bool, str | None]:
    if e2e_mode:
        return (
            branch_name in e2e_branch_options,
            None
            if branch_name in e2e_branch_options
            else "分支不存在，请重新选择有效远端分支",
        )
    status, payload, error = run_gh_json(
        ["api", f"repos/{repo_full_name}/branches/{quote(branch_name, safe='')}"]
    )
    if status == "ok" and isinstance(payload, dict) and _clean(payload.get("name")):
        return True, None
    if status == "not_found":
        return False, "分支不存在，请重新选择有效远端分支"
    return False, error or "无法确认分支状态，请稍后同步"
