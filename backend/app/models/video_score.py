"""VideoScore model — five-dimension content scoring for discovery.

Each scored YouTube video gets:
- virality_score (0-100): view velocity + engagement + recency
- translation_score (0-100): language suitability for Chinese dubbing
- quality_score (0-100): duration, authority, title quality
- market_score (0-100): Chinese market compatibility
- cost_score (0-100): estimated production effort
- composite_score (0-100): weighted sum of above
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class VideoScore(Base, TimestampMixin):
    __tablename__ = "video_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    youtube_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False,
    )

    # Video metadata (denormalized for fast queries)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    channel_name: Mapped[str] = mapped_column(String(256), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(128), nullable=False)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Five dimension scores (0-100 each)
    virality_score: Mapped[float] = mapped_column(Float, default=0.0)
    translation_score: Mapped[float] = mapped_column(Float, default=0.0)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    market_score: Mapped[float] = mapped_column(Float, default=0.0)
    cost_score: Mapped[float] = mapped_column(Float, default=0.0)

    composite_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    weights_used: Mapped[str] = mapped_column(Text, nullable=False)  # JSON

    # Raw input data (for recalculation when weights change)
    raw_metrics: Mapped[str] = mapped_column(Text, nullable=False)  # JSON

    # Metadata
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    scorer_version: Mapped[str] = mapped_column(String(16), default="1.0")

    # LLM-classified content category
    category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Link to local video (if already processed)
    video_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("videos.id", ondelete="SET NULL"), nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<VideoScore(youtube_id='{self.youtube_id}', "
            f"composite={self.composite_score:.1f})>"
        )
