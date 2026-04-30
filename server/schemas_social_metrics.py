"""Social post metrics response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


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


class SocialPostMetricDetailOut(SocialPostMetricOut):
    post_title: Optional[str] = None
    post_body_excerpt: Optional[str] = None
    post_status: Optional[str] = None
    published_at: Optional[datetime] = None
    x_url: Optional[str] = None
    created_at: Optional[datetime] = None


class SocialPostMetricQueryOut(BaseModel):
    items: list[SocialPostMetricDetailOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 20
    offset: int = 0


class SocialPostMetricDailyOut(BaseModel):
    local_date: str
    observed_post_count: int = 0
    metric_row_count: int = 0
    total_impressions: int = 0
    total_likes: int = 0
    total_replies: int = 0
    total_reposts: int = 0
    total_link_clicks: int = 0
    average_engagement: float = 0.0
    top_post: Optional[SocialPostMetricTopPostOut] = None
    last_observed_at: Optional[datetime] = None


class SocialPostMetricDailyQueryOut(BaseModel):
    items: list[SocialPostMetricDailyOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 30
    offset: int = 0
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class SocialPostMetricSummaryOut(BaseModel):
    observed_post_count: int = 0
    metric_row_count: int = 0
    total_impressions: int = 0
    total_likes: int = 0
    total_replies: int = 0
    total_reposts: int = 0
    total_link_clicks: int = 0
    average_engagement: float = 0.0
    top_posts: list[SocialPostMetricTopPostOut] = Field(default_factory=list)
    last_observed_at: Optional[datetime] = None
    diagnostic: Optional[str] = None
