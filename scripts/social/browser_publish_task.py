#!/usr/bin/env python3
"""Browser-assisted publishing helper for non-API social platforms.

This helper deliberately avoids password login, private web APIs, voting,
comment automation, and CAPTCHA/2FA bypass. It opens the relevant platform page
with the task draft copied to the local clipboard so the operator can review and
submit manually.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess  # nosec B404
import sys
import textwrap
import webbrowser
from dataclasses import dataclass

import requests


DEFAULT_API_BASE = os.environ.get("OPS_CONSOLE_API_BASE", "http://localhost:10100/api")
SUPPORTED_PLATFORMS = {
    "devto",
    "hacker_news",
    "v2ex",
    "hashnode",
    "product_hunt",
    "reddit",
}


@dataclass(frozen=True)
class DraftTask:
    id: int
    platform: str
    channel_key: str
    title: str
    body: str
    submission_url: str | None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open a human-gated browser publishing draft."
    )
    parser.add_argument("--task-id", required=True, type=int)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument(
        "--confirm-submit",
        default="",
        help="Reserved for future fixed-selector submit flows. Only YES is accepted; v1 still stops before submit.",
    )
    args = parser.parse_args()
    platform = _normalize_platform(args.platform)
    if platform not in SUPPORTED_PLATFORMS:
        raise SystemExit(
            f"platform {platform!r} is not supported by browser-assisted publishing v1"
        )
    if args.confirm_submit and args.confirm_submit != "YES":
        raise SystemExit("--confirm-submit must be YES when explicitly used")

    task = _fetch_task(args.api_base.rstrip("/"), args.task_id)
    if task.platform != platform:
        raise SystemExit(f"task platform is {task.platform!r}, not {platform!r}")
    target_url = _target_url(task)
    draft = _draft_text(task)
    _copy_to_clipboard(draft)
    print(
        json.dumps(
            {
                "task_id": task.id,
                "platform": task.platform,
                "target_url": target_url,
                "copied_to_clipboard": True,
                "submit_policy": "operator_must_click_final_submit",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(
        "\nDraft copied to clipboard. Review the page and submit manually after Human Gate."
    )
    webbrowser.open(target_url)
    return 0


def _fetch_task(api_base: str, task_id: int) -> DraftTask:
    response = requests.get(
        f"{api_base}/social/distribution/tasks?limit=500", timeout=15
    )
    response.raise_for_status()
    for row in response.json().get("flat", []):
        if int(row.get("id")) == task_id:
            return DraftTask(
                id=task_id,
                platform=_normalize_platform(str(row.get("platform") or "")),
                channel_key=str(row.get("channel_key") or ""),
                title=str(row.get("platform_title") or ""),
                body=str(row.get("platform_body") or ""),
                submission_url=row.get("submission_url"),
            )
    raise SystemExit(f"distribution task {task_id} not found")


def _target_url(task: DraftTask) -> str:
    if task.submission_url:
        return task.submission_url
    if task.platform == "hacker_news":
        return "https://news.ycombinator.com/submit"
    if task.platform == "devto":
        return "https://dev.to/new"
    if task.platform == "hashnode":
        return "https://hashnode.com/draft"
    if task.platform == "product_hunt":
        return "https://www.producthunt.com/posts/new"
    if task.platform == "reddit":
        channel = task.channel_key if task.channel_key.startswith("r/") else ""
        return f"https://www.reddit.com/{channel}/submit".replace("//submit", "/submit")
    if task.platform == "v2ex":
        node = (
            task.channel_key
            if task.channel_key not in {"v2ex.com", ""}
            else "programmer"
        )
        return f"https://www.v2ex.com/new/{node}"
    raise SystemExit(f"unsupported platform {task.platform!r}")


def _draft_text(task: DraftTask) -> str:
    return textwrap.dedent(
        f"""\
        Title:
        {task.title}

        Body:
        {task.body}
        """
    ).strip()


def _copy_to_clipboard(text: str) -> None:
    if sys.platform == "darwin":
        pbcopy = shutil.which("pbcopy")
        if not pbcopy:
            raise SystemExit("pbcopy not found; cannot copy draft to clipboard")
        subprocess.run([pbcopy], input=text, text=True, check=True)  # nosec B603
        return
    print(text)


def _normalize_platform(platform: str) -> str:
    value = platform.strip()
    return "devto" if value == "dev" else value


if __name__ == "__main__":
    raise SystemExit(main())
