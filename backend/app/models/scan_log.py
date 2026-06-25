"""Phase 9: ScanLog model (D9-07).

每次频道扫描的日志条目：found_count / added_count / error_msg.
"""
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.channel import Channel


class ScanLog(Base):
    """扫描日志（不继承 TimestampMixin — 用 scanned_at 单字段足够）."""
    __tablename__ = "scan_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        index=True,
    )
    found_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    added_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    channel: Mapped["Channel"] = relationship("Channel", back_populates="scan_logs")

    def __repr__(self) -> str:
        return f"<ScanLog(id={self.id}, channel_id={self.channel_id}, added={self.added_count})>"
