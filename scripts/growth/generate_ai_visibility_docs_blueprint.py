#!/usr/bin/env python3
"""Export AI Agent Payments docs blueprint for implementation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.growth.ai_visibility_cli import (  # noqa: E402
    pydantic_payload,
    write_json_payload,
)
from server.services.growth.ai_visibility_docs_blueprint import (  # noqa: E402
    ai_agent_payments_docs_blueprint,
)


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Export the Synapse AI Agent Payments docs blueprint as JSON."
    )
    parser.add_argument("--output", help="Write JSON to this path instead of stdout.")
    args = parser.parse_args()

    blueprint = ai_agent_payments_docs_blueprint()
    write_json_payload(pydantic_payload(blueprint), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
