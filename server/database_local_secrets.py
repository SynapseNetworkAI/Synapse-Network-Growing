"""Local encrypted secret tables."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, Integer, Text, UniqueConstraint

from server.database import Base, utcnow


class LocalSecretVersionRow(Base):
    __tablename__ = "local_secret_versions"
    __table_args__ = (
        UniqueConstraint(
            "secret_key", "version", name="local_secret_versions_key_version_uq"
        ),
        Index("local_secret_versions_key_status_idx", "secret_key", "status"),
        Index("local_secret_versions_created_idx", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    secret_key = Column(Text, nullable=False)
    version = Column(Integer, nullable=False)
    ciphertext = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="active")
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


def migrate_local_secret_versions(engine_, tables: set[str]) -> None:
    if "local_secret_versions" not in tables:
        LocalSecretVersionRow.__table__.create(bind=engine_, checkfirst=True)
