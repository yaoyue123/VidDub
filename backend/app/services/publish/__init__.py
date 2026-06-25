"""v3.2 平台发布 — 全部迁移到 social-auto-upload.

Douyin  → SAU DouYinVideo (Playwright browser)
Bilibili → SAU biliup Rust binary
Ixigua  → Playwright browser (SAU 暂无, 保留 you2bili 实现)
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
