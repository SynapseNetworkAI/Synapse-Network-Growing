"""Database rows for SDK package releases."""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from server.database import Base, utcnow


class SdkPackageReleaseRow(Base):
    __tablename__ = "sdk_package_releases"
    __table_args__ = (
        UniqueConstraint(
            "sdk_language",
            "registry",
            "package_version",
            name="sdk_package_release_version_uq",
        ),
        Index("sdk_package_releases_train_idx", "release_train_version"),
        Index("sdk_package_releases_status_idx", "status"),
        Index("sdk_package_releases_language_idx", "sdk_language"),
        Index("sdk_package_releases_registry_idx", "registry"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    release_train_version = Column(Text, nullable=False)
    sdk_language = Column(Text, nullable=False)
    package_name = Column(Text, nullable=False)
    registry = Column(Text, nullable=False)
    channel = Column(Text, nullable=False, default="preview")
    package_version = Column(Text, nullable=False)
    git_tag = Column(Text)
    status = Column(Text, nullable=False, default="planned")
    package_url = Column(Text)
    workflow_run_url = Column(Text)
    failure_summary = Column(Text)
    release_notes = Column(Text)
    metadata_json = Column(Text, nullable=False, default="{}")
    published_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class SdkPackageReleaseEventRow(Base):
    __tablename__ = "sdk_package_release_events"
    __table_args__ = (
        Index("sdk_package_release_events_release_idx", "sdk_package_release_id"),
        Index("sdk_package_release_events_action_idx", "action"),
        Index("sdk_package_release_events_created_idx", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    sdk_package_release_id = Column(
        Integer, ForeignKey("sdk_package_releases.id"), nullable=False
    )
    action = Column(Text, nullable=False)
    from_status = Column(Text)
    to_status = Column(Text)
    actor = Column(Text)
    note = Column(Text)
    workflow_run_url = Column(Text)
    error_summary = Column(Text)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)

    sdk_package_release = relationship("SdkPackageReleaseRow")


class SdkPackagePlatformRow(Base):
    __tablename__ = "sdk_package_platforms"
    __table_args__ = (
        Index("sdk_package_platforms_platform_idx", "platform_key", unique=True),
        Index("sdk_package_platforms_enabled_idx", "enabled"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_key = Column(Text, nullable=False)
    sdk_language = Column(Text, nullable=False)
    registry = Column(Text, nullable=False)
    package_name = Column(Text, nullable=False)
    registry_url = Column(Text, nullable=False)
    package_url_template = Column(Text, nullable=False)
    credential_env_var = Column(Text, nullable=False)
    enabled = Column(Integer, nullable=False, default=0)
    notes = Column(Text)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
