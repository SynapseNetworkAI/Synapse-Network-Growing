"""Social post metrics response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SocialPostMetricTopPostOut(BaseModel):
    post_id: Optional[int] = None
    external_post_id: Optional[str] = None
    title: Optional[str] = None
    impressions: int = 0
    likes: int = 0
    replies: int = 0
    reposts: int = 0
    link_clicks: int = 0
    engagement_total: int = 0
    observed_at: Optional[datetime] = None


class SocialPostMetricOut(BaseModel):
    id: int
    post_id: Optional[int] = None
    external_post_id: Optional[str] = None
    impressions: int = 0
    likes: int = 0
    replies: int = 0
    reposts: int = 0
    follows: int = 0
    link_clicks: int = 0
    summary: Optional[str] = None
    observed_at: Optional[datetime] = None


class SocialPostMetricSummaryOut(BaseModel):
    observed_post_count: int = 0
    metric_row_count: int = 0
    total_impressions: int = 0
    total_likes: int = 0
    total_replies: int = 0
    total_reposts: int = 0
    total_link_clicks: int = 0
    average_engagement: float = 0.0
    top_posts: list[SocialPostMetricTopPostOut] = []
    last_observed_at: Optional[datetime] = None
    diagnostic: Optional[str] = None
