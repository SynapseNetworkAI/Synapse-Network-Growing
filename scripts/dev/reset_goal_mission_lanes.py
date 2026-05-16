#!/usr/bin/env python3
"""Deprecated local SQLite demo reset.

The Ops runtime is PostgreSQL-only. This script used to mutate `server/ops.db`
directly and is intentionally disabled rather than ported as a hidden fallback.
Use the planner / goal APIs or a Postgres-safe SQLAlchemy maintenance script for
new resets.
"""

from __future__ import annotations


def main() -> int:
    print(
        "reset_goal_mission_lanes.py is deprecated because SQLite runtime "
        "fallback has been removed. Use PostgreSQL-backed APIs or write a "
        "Postgres-safe maintenance script instead."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
