"""Phase 9: Channel model (D9-03).

订阅的 YouTube 频道，APScheduler 按 scan_interval_hours 定时扫描。
"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.scan_log import ScanLog
    from app.models.video import Video


class Channel(Base, TimestampMixin):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="频道别名")
    url: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, comment="频道 URL")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", index=True)
    scan_interval_hours: Mapped[int] = mapped_column(Integer, default=6, server_default="6")
    last_scanned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # 过滤条件 (可空 = 不过滤)
    filter_min_views: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    filter_max_duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    filter_min_duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    auto_publish: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    scan_logs: Mapped[list["ScanLog"]] = relationship(
        "ScanLog", back_populates="channel",
        cascade="all, delete-orphan",
        order_by="ScanLog.scanned_at.desc()",
    )
    # Phase 9: 与 Video.source_channel 对应（避免与 Video.channel 字符串列冲突）
    videos: Mapped[list["Video"]] = relationship(
        "Video", back_populates="source_channel",
        foreign_keys="Video.channel_id",
    )

    def __repr__(self) -> str:
        return f"<Channel(id={self.id}, name='{self.name}', enabled={self.enabled})>"
