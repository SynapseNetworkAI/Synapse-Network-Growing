"""Social distribution source-of-truth database rows."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from server.database import Base, utcnow


def migrate_social_distribution_schema(engine_, insp, tables: set[str]) -> None:
    if "social_distribution_accounts" not in tables:
        return
    existing = {c["name"] for c in insp.get_columns("social_distribution_accounts")}
    distribution_account_cols = {
        "publish_mode": "TEXT DEFAULT 'manual_only'",
        "credential_ref": "TEXT",
        "api_capability": "TEXT DEFAULT 'none'",
    }
    for col, col_type in distribution_account_cols.items():
        if col not in existing:
            with engine_.connect() as conn:
                conn.execute(
                    text(
                        f"ALTER TABLE social_distribution_accounts ADD COLUMN {col} {col_type}"
                    )
                )
                conn.commit()


class SocialDistributionAccountRow(Base):
    __tablename__ = "social_distribution_accounts"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "channel_key",
            name="social_distribution_accounts_platform_channel_uq",
        ),
        Index("social_distribution_accounts_platform_idx", "platform"),
        Index("social_distribution_accounts_status_idx", "status"),
        Index("social_distribution_accounts_priority_idx", "priority"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(Text, nullable=False)
    channel_key = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    signup_url = Column(Text)
    profile_url = Column(Text)
    account_type = Column(Text, nullable=False, default="operator")
    priority = Column(Text, nullable=False, default="P1")
    status = Column(Text, nullable=False, default="planned")
    email_hint = Column(Text)
    two_factor_status = Column(Text, nullable=False, default="unknown")
    read_automation_mode = Column(Text, nullable=False, default="manual_only")
    human_publish_required = Column(Boolean, nullable=False, default=True)
    publish_mode = Column(Text, nullable=False, default="manual_only")
    credential_ref = Column(Text)
    api_capability = Column(Text, nullable=False, default="none")
    notes = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    tasks = relationship(
        "SocialDistributionTaskRow",
        order_by="SocialDistributionTaskRow.id",
        back_populates="account",
    )


class SocialContentAssetRow(Base):
    __tablename__ = "social_content_assets"
    __table_args__ = (
        Index("social_content_assets_status_idx", "status"),
        Index("social_content_assets_type_idx", "asset_type"),
        Index("social_content_assets_source_idx", "source_type"),
        Index("social_content_assets_goal_idx", "goal_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_type = Column(Text, nullable=False, default="article")
    source_type = Column(Text, nullable=False, default="manual")
    title = Column(Text, nullable=False)
    body = Column(Text)
    summary = Column(Text)
    canonical_url = Column(Text)
    source_signal_id = Column(Integer)
    goal_key = Column(Text)
    policy_check_json = Column(Text, nullable=False, default="{}")
    agent_metadata_json = Column(Text, nullable=False, default="{}")
    status = Column(Text, nullable=False, default="draft")
    created_by = Column(Text, nullable=False, default="operator")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    tasks = relationship(
        "SocialDistributionTaskRow",
        order_by="SocialDistributionTaskRow.id",
        back_populates="asset",
    )
    events = relationship(
        "SocialDistributionEventRow",
        order_by="SocialDistributionEventRow.id",
        back_populates="asset",
    )
    documents = relationship(
        "SocialDistributionDocumentRow",
        order_by="SocialDistributionDocumentRow.id",
        back_populates="asset",
    )


class SocialDistributionTaskRow(Base):
    __tablename__ = "social_distribution_tasks"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "account_id",
            "action",
            name="social_distribution_tasks_asset_account_action_uq",
        ),
        Index("social_distribution_tasks_asset_idx", "asset_id"),
        Index("social_distribution_tasks_account_idx", "account_id"),
        Index("social_distribution_tasks_status_idx", "status"),
        Index("social_distribution_tasks_platform_idx", "platform"),
        Index("social_distribution_tasks_action_idx", "action"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("social_content_assets.id"), nullable=False)
    account_id = Column(
        Integer, ForeignKey("social_distribution_accounts.id"), nullable=False
    )
    platform = Column(Text, nullable=False)
    channel_key = Column(Text, nullable=False)
    action = Column(Text, nullable=False, default="post")
    status = Column(Text, nullable=False, default="planned")
    platform_title = Column(Text)
    platform_body = Column(Text)
    operator_checklist = Column(Text)
    submission_url = Column(Text)
    published_url = Column(Text)
    external_post_id = Column(Text)
    failure_summary = Column(Text)
    manual_result_note = Column(Text)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    asset = relationship("SocialContentAssetRow", back_populates="tasks")
    account = relationship("SocialDistributionAccountRow", back_populates="tasks")
    events = relationship(
        "SocialDistributionEventRow",
        order_by="SocialDistributionEventRow.id",
        back_populates="task",
    )
    documents = relationship(
        "SocialDistributionDocumentRow",
        order_by="SocialDistributionDocumentRow.id",
        back_populates="task",
    )


class SocialDistributionEventRow(Base):
    __tablename__ = "social_distribution_events"
    __table_args__ = (
        Index("social_distribution_events_asset_idx", "asset_id"),
        Index("social_distribution_events_task_idx", "task_id"),
        Index("social_distribution_events_type_idx", "event_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("social_content_assets.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("social_distribution_tasks.id"))
    event_type = Column(Text, nullable=False)
    actor = Column(Text, nullable=False, default="system")
    summary = Column(Text)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)

    asset = relationship("SocialContentAssetRow", back_populates="events")
    task = relationship("SocialDistributionTaskRow", back_populates="events")


class SocialDistributionDocumentRow(Base):
    __tablename__ = "social_distribution_documents"
    __table_args__ = (
        Index("social_distribution_documents_asset_idx", "asset_id"),
        Index("social_distribution_documents_task_idx", "task_id"),
        Index("social_distribution_documents_kind_idx", "document_kind"),
        Index("social_distribution_documents_status_idx", "status"),
        Index(
            "social_distribution_documents_asset_kind_platform_idx",
            "asset_id",
            "document_kind",
            "platform",
            "channel_key",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("social_content_assets.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("social_distribution_tasks.id"))
    document_kind = Column(Text, nullable=False)
    platform = Column(Text)
    channel_key = Column(Text)
    title = Column(Text, nullable=False)
    body_markdown = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="generated")
    version = Column(Integer, nullable=False, default=1)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    asset = relationship("SocialContentAssetRow", back_populates="documents")
    task = relationship("SocialDistributionTaskRow", back_populates="documents")
