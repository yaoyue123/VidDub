"""Phase 14: Discovery models for intelligent content sourcing."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.discovery_scan_log import DiscoveryScanLog


class DiscoverySource(Base, TimestampMixin):
    __tablename__ = "discovery_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="keyword | creator | playlist | trending | topic",
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

    # Filter conditions (nullable = no filter applied)
    filter_min_views: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="Minimum view count filter",
    )
    filter_max_views: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="Maximum view count filter",
    )
    filter_min_duration_sec: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="Minimum video duration in seconds",
    )
    filter_max_duration_sec: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="Maximum video duration in seconds",
    )
    filter_published_within_hours: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="Only videos published within this many hours",
    )

    scan_logs: Mapped[list["DiscoveryScanLog"]] = relationship(
        "DiscoveryScanLog", back_populates="source",
        cascade="all, delete-orphan",
        order_by="DiscoveryScanLog.scanned_at.desc()",
    )

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

    # Display metadata for results grid (populated during scan)
    view_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    like_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    thumbnail_url: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True,
    )
    published_at: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
        comment="ISO 8601 publish date string from yt-dlp",
    )
    duration_sec: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="Video duration in seconds",
    )

    video_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("videos.id", ondelete="SET NULL"), nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<DiscoveryResult(id={self.id}, youtube_id='{self.youtube_id}', "
            f"status='{self.status}')>"
        )
