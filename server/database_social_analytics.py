"""Social analytics extension tables.

These rows keep X feedback-loop facts separate from the legacy post metric
table so metric observations can stay append-only and lightweight.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, Integer, Text, inspect, text

from server.database import Base, utcnow


class SocialAccountSnapshotRow(Base):
    __tablename__ = "social_account_snapshots"
    __table_args__ = (
        Index("social_account_snapshots_platform_idx", "platform"),
        Index("social_account_snapshots_observed_idx", "observed_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(Text, nullable=False, default="x")
    account_handle = Column(Text, nullable=False)
    followers = Column(Integer, nullable=False, default=0)
    following = Column(Integer, nullable=False, default=0)
    profile_url = Column(Text)
    summary = Column(Text)
    metadata_json = Column(Text, nullable=False, default="{}")
    observed_at = Column(DateTime, nullable=False, default=utcnow)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class SocialWeeklyReviewRow(Base):
    __tablename__ = "social_weekly_reviews"
    __table_args__ = (
        Index("social_weekly_reviews_week_idx", "week_start", "week_end"),
        Index("social_weekly_reviews_status_idx", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(Text, nullable=False, default="x")
    week_start = Column(DateTime, nullable=False)
    week_end = Column(DateTime, nullable=False)
    status = Column(Text, nullable=False, default="succeeded")
    summary = Column(Text)
    best_topics_json = Column(Text, nullable=False, default="[]")
    best_hooks_json = Column(Text, nullable=False, default="[]")
    low_performing_patterns_json = Column(Text, nullable=False, default="[]")
    recommendations_json = Column(Text, nullable=False, default="[]")
    content_generation_guidance_json = Column(Text, nullable=False, default="{}")
    source_metric_ids_json = Column(Text, nullable=False, default="[]")
    error_excerpt = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


def migrate_social_analytics_schema(engine_, insp, tables: set[str]) -> None:
    if "social_account_snapshots" not in tables:
        SocialAccountSnapshotRow.__table__.create(bind=engine_, checkfirst=True)
    if "social_weekly_reviews" not in tables:
        SocialWeeklyReviewRow.__table__.create(bind=engine_, checkfirst=True)
    if "social_post_metrics" in tables:
        current_insp = inspect(engine_)
        existing = {c["name"] for c in current_insp.get_columns("social_post_metrics")}
        if "metadata_json" not in existing:
            with engine_.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE social_post_metrics "
                        "ADD COLUMN metadata_json TEXT DEFAULT '{}' NOT NULL"
                    )
                )
