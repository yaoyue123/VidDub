"""Phase 17: PerformanceLog model for tracking content performance."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PerformanceLog(Base, TimestampMixin):
    __tablename__ = "performance_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    youtube_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # Platform performance
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_views: Mapped[int] = mapped_column(Integer, default=0)
    platform_likes: Mapped[int] = mapped_column(Integer, default=0)
    platform_comments: Mapped[int] = mapped_column(Integer, default=0)
    platform_shares: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    platform_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Score comparison
    predicted_score: Mapped[float] = mapped_column(Float, default=0.0)
    actual_score: Mapped[float] = mapped_column(Float, default=0.0)
    score_accuracy: Mapped[float] = mapped_column(Float, default=0.0)

    # Metadata
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetch_method: Mapped[str] = mapped_column(
        String(16), default="manual",
        comment="api | manual | estimated",
    )

    def __repr__(self) -> str:
        return (
            f"<PerformanceLog(video={self.video_id}, platform='{self.platform}', "
            f"score_accuracy={self.score_accuracy:.1f})>"
        )
