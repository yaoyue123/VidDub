from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    pass


class Subtitle(Base, TimestampMixin):
    """Stores subtitle content for videos.

    Supports multiple languages per video. The 'source' field tracks
    whether the subtitle is from Whisper transcription, manual editing,
    or LLM translation.
    """

    __tablename__ = "subtitles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(
        String(32),
        default="whisper",
        comment="whisper / manual / translation",
    )
    content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="SRT or JSON formatted subtitle content",
    )
    filepath: Mapped[Optional[str]] = mapped_column(
        String(1024), nullable=True,
        comment="Path to SRT file on disk",
    )

    def __repr__(self) -> str:
        return f"<Subtitle(id={self.id}, video_id={self.video_id}, lang='{self.language}')>"
