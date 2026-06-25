"""Phase 14: Discovery models for intelligent content sourcing."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DiscoverySource(Base, TimestampMixin):
    __tablename__ = "discovery_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="channel | keyword | category | trending",
    )
    source_value: Mapped[str] = mapped_column(
        String(512), nullable=False,
        comment="Channel URL / search keyword / category name",
    )
    label: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="Human-readable name",
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scanned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    scan_interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    max_results_per_scan: Mapped[int] = mapped_column(Integer, default=20)

    def __repr__(self) -> str:
        return (
            f"<DiscoverySource(id={self.id}, type='{self.type}', "
            f"label='{self.label}')>"
        )


class DiscoveryResult(Base, TimestampMixin):
    __tablename__ = "discovery_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("discovery_sources.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    youtube_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    channel_name: Mapped[str] = mapped_column(String(256), nullable=False)
    composite_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="new",
        comment="new | scored | dubbed | ignored",
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    video_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("videos.id", ondelete="SET NULL"), nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<DiscoveryResult(id={self.id}, youtube_id='{self.youtube_id}', "
            f"status='{self.status}')>"
        )
