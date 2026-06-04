from __future__ import annotations

import logging

from sqlalchemy import text

logger = logging.getLogger("ops-dashboard.db")


def migrate_growth_ai_visibility_schema(engine_, insp, tables: set[str]) -> None:
    if "growth_ai_visibility_checks" not in tables:
        return

    existing = {c["name"] for c in insp.get_columns("growth_ai_visibility_checks")}
    ai_visibility_cols = {
        "feed_key": "TEXT DEFAULT ''",
        "run_group": "TEXT DEFAULT ''",
        "result_rank": "INTEGER DEFAULT 0",
        "evidence_url": "TEXT DEFAULT ''",
        "metadata_json": "TEXT DEFAULT '{}'",
    }
    for col, col_type in ai_visibility_cols.items():
        if col not in existing:
            logger.info(
                "Migrating: adding '%s' column to growth_ai_visibility_checks table",
                col,
            )
            with engine_.connect() as conn:
                conn.execute(
                    text(
                        f"ALTER TABLE growth_ai_visibility_checks ADD COLUMN {col} {col_type}"
                    )
                )
                conn.commit()
