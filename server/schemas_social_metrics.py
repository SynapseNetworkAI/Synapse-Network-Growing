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
    profile_visits: int = 0
    bookmarks: int = 0
    engagement_total: int = 0
    topic_tags: list[str] = Field(default_factory=list)
    hook_text: Optional[str] = None
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
    profile_visits: int = 0
    bookmarks: int = 0
    format_kind: Optional[str] = None
    posted_at: Optional[datetime] = None
    summary: Optional[str] = None
    content_type: Optional[str] = None
    post_intent: Optional[str] = None
    source_strategy: Optional[str] = None
    hook_text: Optional[str] = None
    topic_tags: list[str] = Field(default_factory=list)
    has_media: bool = False
    has_thread: bool = False
    has_url: bool = False
    human_link_reason: Optional[str] = None
    negative_feedback_count: int = 0
    subscription_conversions: int = 0
    metric_source: Optional[str] = None
    diagnostic: Optional[str] = None
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
    total_profile_visits: int = 0
    total_bookmarks: int = 0
    total_negative_feedback: int = 0
    total_subscription_conversions: int = 0
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
    total_profile_visits: int = 0
    total_bookmarks: int = 0
    average_engagement: float = 0.0
    top_posts: list[SocialPostMetricTopPostOut] = Field(default_factory=list)
    last_observed_at: Optional[datetime] = None
    diagnostic: Optional[str] = None


class SocialPostMetricManualCreateRequest(BaseModel):
    external_post_id: Optional[str] = None
    impressions: int = 0
    likes: int = 0
    replies: int = 0
    reposts: int = 0
    follows: int = 0
    link_clicks: int = 0
    profile_visits: int = 0
    bookmarks: int = 0
    format_kind: Optional[str] = None
    posted_at: Optional[datetime] = None
    summary: Optional[str] = None
    observed_at: Optional[datetime] = None
    content_type: Optional[str] = None
    post_intent: Optional[str] = None
    source_strategy: Optional[str] = None
    hook_text: Optional[str] = None
    topic_tags: list[str] = Field(default_factory=list)
    has_media: bool = False
    has_thread: bool = False
    has_url: bool = False
    human_link_reason: Optional[str] = None
    negative_feedback_count: int = 0
    subscription_conversions: int = 0


class SocialAccountSnapshotOut(BaseModel):
    id: int
    platform: str = "x"
    account_handle: str
    followers: int = 0
    following: int = 0
    followers_delta: int = 0
    profile_url: Optional[str] = None
    summary: Optional[str] = None
    observed_at: Optional[datetime] = None


class SocialAccountSnapshotQueryOut(BaseModel):
    items: list[SocialAccountSnapshotOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 30
    offset: int = 0


class SocialWeeklyReviewOut(BaseModel):
    id: int
    platform: str = "x"
    week_start: datetime
    week_end: datetime
    status: str
    summary: Optional[str] = None
    best_topics: list[dict] = Field(default_factory=list)
    best_hooks: list[dict] = Field(default_factory=list)
    low_performing_patterns: list[dict] = Field(default_factory=list)
    recommendations: list[dict] = Field(default_factory=list)
    content_generation_guidance: dict = Field(default_factory=dict)
    source_metric_ids: list[int] = Field(default_factory=list)
    error_excerpt: Optional[str] = None
    created_at: Optional[datetime] = None


class SocialWeeklyReviewQueryOut(BaseModel):
    items: list[SocialWeeklyReviewOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 12
    offset: int = 0


class SocialWeeklyReviewRunRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=30)
    dry_run: bool = False
