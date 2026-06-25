from typing import Optional

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Config(Base, TimestampMixin):
    __tablename__ = "configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    def __repr__(self) -> str:
        return f"<Config(key='{self.key}')>"
