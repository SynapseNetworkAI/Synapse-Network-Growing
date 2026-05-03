"""GitHub Actions log projection helpers for release deployments."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class GitHubFailureLogResult:
    excerpt: str | None
    metadata: dict[str, Any]
    note: str


_ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
_FAILED_LOG_MARKERS = (
    "##[error]",
    "error:",
    "failed",
    "unauthorized_client",
    "attribute condition",
    "permission",
    "denied",
    "not found",
)


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def _bounded_error_excerpt(value: str, limit: int = 500) -> str:
    cleaned = _clean(value).replace("\r", "")
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}... [Truncated]"


def _clean_actions_log_line(value: str) -> str:
    line = _ANSI_ESCAPE_RE.sub("", str(value or "").replace("\r", "")).strip()
    if "\t" in line:
        line = line.split("\t")[-1].strip()
    line = re.sub(r"^\d{4}-\d{2}-\d{2}T[0-9:.]+Z\s*", "", line)
    return line.strip()


def _select_failure_lines(lines: list[str]) -> list[str]:
    selected = [
        line
        for line in lines
        if any(marker in line.lower() for marker in _FAILED_LOG_MARKERS)
    ]
    return selected or lines[-8:]


def _dedupe_log_lines(lines: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for line in lines:
        cleaned = _bounded_error_excerpt(line, 500)
        if cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
        if len(deduped) >= 8:
            break
    return deduped


def _extract_github_failed_log_excerpt(log_text: str | None) -> str | None:
    lines = [_clean_actions_log_line(line) for line in str(log_text or "").splitlines()]
    useful = [line for line in lines if line]
    if not useful:
        return None
    deduped = _dedupe_log_lines(_select_failure_lines(useful))
    if not deduped:
        return None
    return _bounded_error_excerpt("\n".join(deduped), 1500)


def _failure_note(conclusion: str, excerpt: str | None = None) -> str:
    base = f"GitHub Actions staging deploy {conclusion or 'failed'}."
    if not excerpt:
        return base
    return _bounded_error_excerpt(f"{base}\n{excerpt}", 1500)


def github_failure_log_result(
    repo_full_name: str,
    run_id: str,
    *,
    conclusion: str,
    run_gh_text: Callable[[list[str]], tuple[str, str | None, str]],
) -> GitHubFailureLogResult:
    status, text, error = run_gh_text(
        ["run", "view", str(run_id), "--repo", repo_full_name, "--log-failed"]
    )
    if status != "ok":
        diagnostic = _bounded_error_excerpt(
            error
            or (
                "Unable to read GitHub Actions failed logs. Configure the backend GitHub token with "
                "repo access and Actions read permission for this repository."
            ),
            1200,
        )
        return GitHubFailureLogResult(
            excerpt=None,
            metadata={
                "githubFailureLogStatus": status,
                "githubFailureLogError": diagnostic,
            },
            note=_failure_note(conclusion),
        )
    excerpt = _extract_github_failed_log_excerpt(text)
    if not excerpt:
        return GitHubFailureLogResult(
            excerpt=None,
            metadata={
                "githubFailureLogStatus": "empty",
                "githubFailureLogError": "GitHub Actions failed log output was empty or did not contain a readable failed step.",
            },
            note=_failure_note(conclusion),
        )
    return GitHubFailureLogResult(
        excerpt=excerpt,
        metadata={
            "githubFailureLogStatus": "ok",
            "githubFailureLogExcerpt": excerpt,
        },
        note=_failure_note(conclusion, excerpt),
    )
