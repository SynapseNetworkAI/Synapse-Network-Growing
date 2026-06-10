#!/usr/bin/env python3
"""Export AI visibility external-probe readiness and API key gate evidence."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.growth.ai_visibility_cli import (  # noqa: E402
    pydantic_payload,
    write_json_payload,
)
from scripts.growth.local_env import load_optional_dotenv_path  # noqa: E402
from server.services.growth.ai_visibility_external_probe_gate import (  # noqa: E402
    DEFAULT_FEED_KEY,
    ai_visibility_external_probe_gate,
)


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Export fail-closed GPT/Claude/Grok/Gemini probe gate evidence."
    )
    parser.add_argument("--feed-key", default=DEFAULT_FEED_KEY)
    parser.add_argument("--run-group", default="")
    parser.add_argument(
        "--env-file",
        default=str(PROJECT_ROOT / ".env"),
        help=(
            "Load answer-engine probe key presence from this dotenv file without "
            "overriding exported values. Also supported through AI_VISIBILITY_ENV_FILE."
        ),
    )
    parser.add_argument("--output", help="Write JSON to this path instead of stdout.")
    args = parser.parse_args()

    if os.environ.get("AI_VISIBILITY_SKIP_DOTENV", "").strip() != "1":
        load_optional_dotenv_path(
            os.environ.get("AI_VISIBILITY_ENV_FILE", "").strip() or args.env_file
        )

    gate = ai_visibility_external_probe_gate(
        feed_key=args.feed_key,
        run_group=args.run_group or None,
    )
    write_json_payload(pydantic_payload(gate), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
