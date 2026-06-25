"""Phase 6: 平台登录服务命名空间.

提供哔哩哔哩 / 西瓜视频的扫码登录、登录态持久化、过期检测能力。
"""
from app.services.platform.manager import LoginManager  # noqa: F401

__all__ = ["LoginManager"]
