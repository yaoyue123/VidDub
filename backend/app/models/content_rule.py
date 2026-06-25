"""Phase 15: ContentRule model for custom scoring rules."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ContentRule(Base, TimestampMixin):
    __tablename__ = "content_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)

    # Scoring weights (JSON: {"virality": 0.30, ...})
    weights: Mapped[str] = mapped_column(Text, nullable=False)

    # Filter conditions (JSON array)
    # [{"field": "view_count", "op": "gte", "value": 50000}, ...]
    conditions: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Whitelist/blacklist (JSON arrays)
    whitelist_channels: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    blacklist_keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    blacklist_channels: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Output control
    max_results: Mapped[int] = mapped_column(Integer, default=20)
    auto_create_dub: Mapped[bool] = mapped_column(Boolean, default=False)

    # UI ordering
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    last_evaluated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    def __repr__(self) -> str:
        return f"<ContentRule(id={self.id}, name='{self.name}')>"
