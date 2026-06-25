"""Phase 7 publish_record 模型 (D7-05).

记录每次发布到外部平台 (Bilibili/Ixigua) 的尝试与结果。
"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.video import Video


class PublishStatus:
    """publish_record.status 字段取值."""
    PENDING = "pending"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"


class PublishPlatform:
    """支持的平台标识 (v3.2 — 新增 douyin, 全部托管给 social-auto-upload)."""
    DOUYIN = "douyin"
    BILIBILI = "bilibili"
    IXIGUA = "ixigua"


class PublishRecord(Base, TimestampMixin):
    """单次发布尝试的记录.

    一个视频 (video_id) 可以有多条记录（每个平台多次重试）。
    UI 通常按 (video_id, platform) 分组显示最新一条。
    """
    __tablename__ = "publish_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True, nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), default=PublishStatus.PENDING, index=True
    )

    # 发布成功后拿到的平台视频 URL
    platform_video_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # 填表时使用的字段（用于审计 / 重试）
    title_used: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    desc_used: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags_used: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    cover_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    category_used: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    copyright_used: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    needs_relogin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    video: Mapped["Video"] = relationship("Video", backref="publish_records")

    def __repr__(self) -> str:
        return (
            f"<PublishRecord(id={self.id}, video_id={self.video_id}, "
            f"platform='{self.platform}', status='{self.status}')>"
        )
