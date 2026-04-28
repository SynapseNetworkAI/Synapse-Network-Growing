#!/usr/bin/env python3
"""Fail only on high/critical Yarn audit findings."""

from __future__ import annotations

import json
import subprocess  # nosec
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "dashboard"
BLOCKING = {"high", "critical"}


def main() -> int:
    completed = subprocess.run(  # nosec
        ["yarn", "audit", "--json"],
        cwd=DASHBOARD,
        check=False,
        capture_output=True,
        text=True,
    )
    blocking_counts = {severity: 0 for severity in BLOCKING}
    for line in completed.stdout.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") != "auditSummary":
            continue
        vulnerabilities = payload.get("data", {}).get("vulnerabilities", {})
        for severity in BLOCKING:
            blocking_counts[severity] = int(vulnerabilities.get(severity) or 0)

    total = sum(blocking_counts.values())
    if total:
        print(
            f"[quality:yarn-audit] high/critical vulnerabilities found: {blocking_counts}",
            file=sys.stderr,
        )
        return 1
    print("[quality:yarn-audit] ok (no high/critical vulnerabilities)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
