"""DiscoveryScanLog model (Phase 8).

Each scan of a DiscoverySource produces one log entry:
timestamp, found count, added count, status, optional error message.
"""
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.discovery import DiscoverySource


class DiscoveryScanLog(Base):
    """Scan log for DiscoverySource scans (not inherited from TimestampMixin --
    scanned_at single-field timestamp is sufficient, mirroring ScanLog pattern).
    """
    __tablename__ = "discovery_scan_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("discovery_sources.id", ondelete="CASCADE"),
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
    status: Mapped[str] = mapped_column(
        String(16), default="success", server_default="success",
        comment="success | partial | failed",
    )
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    source: Mapped["DiscoverySource"] = relationship(
        "DiscoverySource", back_populates="scan_logs",
    )

    def __repr__(self) -> str:
        return (
            f"<DiscoveryScanLog(id={self.id}, source_id={self.source_id}, "
            f"status='{self.status}', added={self.added_count})>"
        )
