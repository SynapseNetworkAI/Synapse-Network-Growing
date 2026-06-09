"""Read-only spot checks for source-host public listing visibility."""

from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from server.schemas_growth import GrowthAIVisibilitySourceHostLiveSpotCheckOut
from server.services.growth.ai_visibility_presence_plan import DEFAULT_FEED_KEY
from server.services.growth.ai_visibility_source_host_feed import (
    ai_visibility_source_host_execution_checklist,
)
from server.services.growth.ai_visibility_source_host_offline_live import (
    source_host_live_spot_check_from_checklist_model,
)


def ai_visibility_source_host_live_spot_check(
    db: Session,
    *,
    feed_key: str = DEFAULT_FEED_KEY,
    run_group: str | None = None,
    execute: bool = False,
    fetcher: Callable[[str], tuple[int, str]] | None = None,
) -> GrowthAIVisibilitySourceHostLiveSpotCheckOut:
    checklist = ai_visibility_source_host_execution_checklist(
        db,
        feed_key=feed_key,
        run_group=run_group,
    )
    return source_host_live_spot_check_from_checklist_model(
        checklist,
        execute=execute,
        fetcher=fetcher,
        execute_command=(
            "python scripts/growth/generate_ai_visibility_source_host_live_spot_check.py "
            f"--feed-key {checklist.feed_key} --execute "
            "--output docs/archive/evidence/growth/ai-visibility/"
            "YYYY-MM-DD-source-host-live-spot-check.json"
        ),
    )
