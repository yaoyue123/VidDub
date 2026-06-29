"""v3.2 平台发布 — 全部由 social-auto-upload 驱动.

Douyin / Kuaishou / Tencent / Xiaohongshu → SAU Playwright browser uploaders
Bilibili → SAU biliup Rust binary
"""
from app.services.publish.base import (  # noqa: F401
    PlatformPublisher,
    PublishFields,
    PublishResult,
)
from app.services.publish.manager import (  # noqa: F401
    PublishManager,
    get_publish_manager,
)

__all__ = [
    "PlatformPublisher",
    "PublishFields",
    "PublishResult",
    "PublishManager",
    "get_publish_manager",
]
