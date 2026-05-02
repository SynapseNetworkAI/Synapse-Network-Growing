#!/usr/bin/env python3
"""Check required @synapse-context tags used by content generation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from server.services.social.context_tags import check_required_context_tags  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--ref-key", action="append", dest="ref_keys")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = check_required_context_tags(
        ref_keys=args.ref_keys,
        workspace_root=args.workspace_root,
    )
    payload = result.model_dump()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        for snippet in result.snippets:
            print(
                f"[context-tags] ok {snippet.ref_key} "
                f"{snippet.file_path}#{snippet.content_hash}"
            )
        for ref_key in result.missing:
            print(
                "[context-tags] missing "
                f"{ref_key}: this tag is required by Synapse content generation.",
                file=sys.stderr,
            )
    return 1 if result.missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
