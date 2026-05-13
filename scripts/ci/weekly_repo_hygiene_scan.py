#!/usr/bin/env python3
"""Read-only weekly repository hygiene scanner."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.services.scheduling.repo_hygiene import scan_repo_hygiene_payload  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=["json"], default="json")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)

    payload = scan_repo_hygiene_payload(root=Path(args.root).resolve())
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
