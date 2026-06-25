from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.task import Task
    from app.models.channel import Channel


class Video(Base, TimestampMixin):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    youtube_url: Mapped[str] = mapped_column(String(512), nullable=False)
    youtube_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    channel: Mapped[str] = mapped_column(String(256), nullable=False)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    view_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    like_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comment_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    filepath: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    dubbed_filepath: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    dubbed_subtitled_filepath: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # ── Rich metadata for upload/publishing ──
    title_en: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    title_zh: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    tags_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON: ["tag1","tag2"]
    tags_zh: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON: ["标签1","标签2"]
    description_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description_zh: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Background audio separation + voice cloning ──
    cloned_voice_uri: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    cloned_voice_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    voice_selection_method: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True,
    )  # "cloned" | "auto_pitch" | "manual" | "default"

    # ── Phase 8: AI 智能标题与标签 (D8-09, D8-10) ──
    # JSON 序列化字符串：["标题1","标题2",...]
    ai_title_candidates: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_tags_candidates: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 用户最终选择的标题/标签 (发布时优先使用)
    title_chosen: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # JSON 序列化字符串：["标签1","标签2",...]
    tags_chosen: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Phase 9: 软删除 + 频道来源 ──
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    channel_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    source: Mapped[str] = mapped_column(String(16), default="manual", server_default="manual")

    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="video", cascade="all, delete-orphan")
    # Phase 9: FK 关系命名为 source_channel 避免与 channel 字符串列冲突 (Phase 1-8 兼容)
    source_channel: Mapped[Optional["Channel"]] = relationship(
        "Channel", back_populates="videos", foreign_keys=[channel_id],
    )

    def __repr__(self) -> str:
        return f"<Video(id={self.id}, youtube_id='{self.youtube_id}', title='{self.title[:30]}')>"
