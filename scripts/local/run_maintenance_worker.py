#!/usr/bin/env python3
"""Run local maintenance jobs that replaced scheduled GitHub workflows."""

from __future__ import annotations

import argparse
import subprocess  # nosec B404
import sys
from pathlib import Path


JOBS = {
    "synapse-weekly-hygiene": (
        Path("/Users/cliff/workspace/agent/Synapse-Network"),
        ["npm", "run", "weekly:hygiene"],
    ),
    "synapse-weekly-hygiene-evidence": (
        Path("/Users/cliff/workspace/agent/Synapse-Network"),
        ["npm", "run", "ci:weekly-hygiene-evidence"],
    ),
    "docs-hygiene": (
        Path("/Users/cliff/workspace/agent/Synapse-Network-Docs"),
        [
            "/bin/bash",
            "-lc",
            "test ! -x scripts/ci/docs_hygiene.sh || scripts/ci/docs_hygiene.sh",
        ],
    ),
    "mcp-ci": (
        Path("/Users/cliff/workspace/agent/Synapse-Network-MCP-Server"),
        [
            "/bin/bash",
            "-lc",
            "npm ci && npm run verify:mcp && npm run smoke:cli && npm pack --dry-run && npm run ci:quality",
        ],
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job", choices=sorted(JOBS))
    args = parser.parse_args()
    cwd, command = JOBS[args.job]
    if not cwd.exists():
        print(f"repo path not found: {cwd}", file=sys.stderr)
        return 2
    print(f"[local-maintenance] job={args.job} cwd={cwd}")
    return subprocess.run(command, cwd=str(cwd), check=False).returncode  # nosec B603


if __name__ == "__main__":
    raise SystemExit(main())
