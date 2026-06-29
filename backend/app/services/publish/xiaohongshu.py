"""Xiaohongshu publisher using social-auto-upload's XiaoHongShuVideo class.

Wraps SAU's Playwright-based xiaohongshu uploader into viddub's
PlatformPublisher interface. Uses SAU's cookie/account file format
at social-auto-upload/cookies/xiaohongshu_{account}.json.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Optional

from app.services.publish.base import (
    PlatformPublisher,
    PublishFields,
    PublishResult,
    UPLOAD_TIMEOUT_SEC,
)

logger = logging.getLogger(__name__)

_SAU_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "social-auto-upload")
)
if os.path.isdir(_SAU_DIR) and _SAU_DIR not in sys.path:
    sys.path.insert(0, _SAU_DIR)


class XiaohongshuPublisher(PlatformPublisher):
    """Xiaohongshu publisher wrapping SAU's XiaoHongShuVideo Playwright uploader."""

    platform = "xiaohongshu"

    def __init__(
        self,
        storage_state_path: str,
        upload_timeout: int = UPLOAD_TIMEOUT_SEC,
        headless: bool = False,
    ) -> None:
        self.storage_state_path = storage_state_path
        self.upload_timeout = upload_timeout
        self.headless = headless

    async def validate_login(self) -> bool:
        """Check if xiaohongshu account file is valid using SAU's cookie_auth."""
        if not os.path.exists(self.storage_state_path):
            logger.warning("Xiaohongshu account file missing: %s", self.storage_state_path)
            return False

        try:
            from uploader.xiaohongshu_uploader.main import xiaohongshu_setup

            result = await xiaohongshu_setup(
                self.storage_state_path,
                handle=False,
                return_detail=True,
                headless=True,
            )
            return bool(result.get("success"))
        except ImportError as e:
            logger.warning("SAU xiaohongshu uploader import error: %s", e)
            return False
        except Exception as e:
            logger.warning("Xiaohongshu validate_login exception: %s", e)
            return False

    async def publish(
        self,
        video_id: int,
        fields: PublishFields,
        video_file_path: str,
        progress_callback: Optional[Any] = None,
    ) -> PublishResult:
        """Publish video to xiaohongshu via SAU's XiaoHongShuVideo."""
        if not os.path.exists(video_file_path):
            return PublishResult(
                success=False,
                error_msg=f"视频文件不存在: {video_file_path}",
            )

        if not os.path.exists(self.storage_state_path):
            return PublishResult(
                success=False,
                error_msg="未登录小红书 (account file 缺失)",
                needs_relogin=True,
            )

        await self._report_progress(progress_callback, "preparing", 5)

        try:
            from uploader.xiaohongshu_uploader.main import XiaoHongShuVideo

            tags = [t.replace("#", "").strip()[:10] for t in (fields.tags or []) if t.strip()]
            if not tags:
                tags = ["科技", "AI", "搬运"]

            title = self._safe_text(fields.title, 80)
            desc = self._safe_text(fields.description, 2000) or title

            uploader = XiaoHongShuVideo(
                title=title,
                file_path=video_file_path,
                tags=tags,
                desc=desc,
                publish_date=0,
                account_file=self.storage_state_path,
                headless=self.headless,
                debug=self.headless is False,
                publish_strategy="immediate",
            )

            await self._report_progress(progress_callback, "uploading", 15)
            await uploader.xiaohongshu_upload_video()

            await self._report_progress(progress_callback, "completed", 100)
            logger.info("Xiaohongshu publish success for video %d", video_id)

            return PublishResult(
                success=True,
                platform_video_url="https://creator.xiaohongshu.com/",
            )

        except ImportError as e:
            logger.error("SAU xiaohongshu import error: %s", e)
            return PublishResult(
                success=False,
                error_msg=f"social-auto-upload 小红书模块不可用: {e}",
            )
        except Exception as e:
            logger.error("Xiaohongshu publish error: %s", e, exc_info=True)
            error_str = str(e)
            needs_relogin = any(
                kw in error_str.lower()
                for kw in ["cookie", "login", "登录", "失效", "expired"]
            )
            return PublishResult(
                success=False,
                error_msg=f"小红书发布失败: {error_str}",
                needs_relogin=needs_relogin,
            )

    @staticmethod
    async def _report_progress(
        callback: Optional[Any], stage: str, pct: float,
    ) -> None:
        if callback:
            try:
                await callback(stage, pct)
            except Exception:
                pass
