#!/usr/bin/env python3
"""Export a bounded AI visibility release blocker snapshot."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.services.growth.ai_visibility_release_snapshot import (  # noqa: E402
    build_snapshot,
)
from server.services.growth.ai_visibility_release_unblock import (  # noqa: E402
    DEFAULT_ACTOR,
    DEFAULT_TARGET_COMMIT,
)

PROBE_ENV_KEYS = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "GEMINI_API_KEY",
    "GENIMI_API_KEY",
}


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Export current AI visibility release blockers as JSON evidence."
    )
    parser.add_argument("--target-commit", default=DEFAULT_TARGET_COMMIT)
    parser.add_argument("--actor", default=DEFAULT_ACTOR)
    parser.add_argument("--feed-key", default="mcp_paid_api_discovery")
    parser.add_argument("--run-group", default="")
    parser.add_argument(
        "--env-file",
        default=str(PROJECT_ROOT / ".env"),
        help="Load answer-engine probe key presence from this dotenv file without overriding exported values.",
    )
    parser.add_argument("--output", help="Write JSON to this path instead of stdout.")
    args = parser.parse_args()

    load_probe_env_file(Path(args.env_file))
    payload = build_snapshot(
        target_commit=args.target_commit,
        actor=args.actor,
        feed_key=args.feed_key,
        run_group=args.run_group,
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


def load_probe_env_file(path: Path) -> None:
    if os.environ.get("AI_VISIBILITY_SKIP_DOTENV", "").strip() == "1":
        return
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        parsed = parse_env_line(raw)
        if parsed is None:
            continue
        key, value = parsed
        if key not in PROBE_ENV_KEYS or os.environ.get(key, "").strip():
            continue
        os.environ[key] = value


def parse_env_line(raw: str) -> tuple[str, str] | None:
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    key, value = line.split("=", 1)
    return key.strip(), unquote_env_value(value)


def unquote_env_value(value: str) -> str:
    clean = value.strip()
    if len(clean) >= 2 and clean[0] == clean[-1] and clean[0] in {"'", '"'}:
        return clean[1:-1]
    return clean


if __name__ == "__main__":
    raise SystemExit(main())
