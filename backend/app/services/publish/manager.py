"""Publish orchestrator (v3.2 — full social-auto-upload migration).

Platform dispatch and metadata are owned by `app.services.platforms.registry`.
This module orchestrates the publish lifecycle (record creation, WebSocket
broadcasts, retries) and delegates the actual upload to the platform's
publisher class resolved via the registry.
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.websocket import manager as ws_manager
from app.models.publish_record import (
    PublishPlatform,
    PublishRecord,
    PublishStatus,
)
from app.services.platforms.registry import (
    all_platforms,
    cookie_path,
    get as get_descriptor,
    is_sau_native,
)
from app.services.publish.base import (
    PlatformPublisher,
    PublishFields,
    PublishResult,
)

logger = logging.getLogger(__name__)


class PublishManager:
    SUPPORTED_PLATFORMS = all_platforms()

    def __init__(self) -> None:
        self._instances: dict[str, PlatformPublisher] = {}

    def get(self, platform: str) -> PlatformPublisher:
        descriptor = get_descriptor(platform)  # raises ValueError for unknown
        if platform in self._instances:
            return self._instances[platform]

        module = importlib.import_module(descriptor.publisher_module)
        cls = getattr(module, descriptor.publisher_class)
        inst: PlatformPublisher = cls(storage_state_path=descriptor.cookie_file)

        self._instances[platform] = inst
        return inst

    def _resolve_account_file(self, platform: str) -> Optional[str]:
        """Resolve account/cookie file path for SAU-based platforms."""
        if is_sau_native(platform):
            return cookie_path(platform)
        return None

    async def publish_to_platform(
        self,
        video_id: int,
        platform: str,
        fields: PublishFields,
        video_file_path: str,
        record_id: Optional[int] = None,
    ) -> PublishResult:
        """发布到单平台.

        Args:
            record_id: 可选的现有 PublishRecord.id（重试时复用）
        """
        # 1. 创建 / 复用 record
        async with async_session_factory() as session:
            if record_id:
                record = (await session.execute(
                    select(PublishRecord).where(PublishRecord.id == record_id)
                )).scalar_one_or_none()
                if not record:
                    raise ValueError(f"PublishRecord {record_id} not found")
                record.retry_count += 1
                record.status = PublishStatus.PUBLISHING
                record.error_msg = None
                record.needs_relogin = False
            else:
                record = PublishRecord(
                    video_id=video_id,
                    platform=platform,
                    status=PublishStatus.PUBLISHING,
                    title_used=fields.title,
                    desc_used=fields.description,
                    tags_used=",".join(fields.tags),
                    cover_path=fields.cover_path,
                    category_used=fields.category_id,
                    copyright_used=fields.copyright_type,
                    started_at=datetime.now(timezone.utc),
                )
                session.add(record)
            await session.commit()
            await session.refresh(record)
            rid = record.id

        # 2. 广播 start
        await ws_manager.broadcast({
            "type": "publish_start",
            "data": {"video_id": video_id, "platform": platform, "record_id": rid},
        })

        # 2b. 同步 cookies 到 social-auto-upload 格式 (最佳努力, 仅 bilibili)
        if platform == PublishPlatform.BILIBILI:
            try:
                from app.services.publish.cookie_bridge import sync_storage_state_to_sau
                sync_storage_state_to_sau("bilibili")
            except Exception as e:
                logger.debug("Cookie sync to social-auto-upload skipped: %s", e)

        publisher = self.get(platform)

        # 3. 进度回调
        async def _progress(stage: str, pct: float):
            await ws_manager.broadcast({
                "type": "publish_progress",
                "data": {
                    "video_id": video_id,
                    "platform": platform,
                    "record_id": rid,
                    "stage": stage,
                    "pct": pct,
                },
            })

        # 4. 执行
        try:
            result = await publisher.publish(
                video_id=video_id,
                fields=fields,
                video_file_path=video_file_path,
                progress_callback=_progress,
            )
        except Exception as e:
            logger.error("publish_to_platform crashed: %s", e, exc_info=True)
            result = PublishResult(success=False, error_msg=str(e))

        # 5. 更新 record
        async with async_session_factory() as session:
            now = datetime.now(timezone.utc)
            if result.success:
                await session.execute(
                    update(PublishRecord).where(PublishRecord.id == rid).values(
                        status=PublishStatus.PUBLISHED,
                        platform_video_url=result.platform_video_url,
                        completed_at=now,
                        error_msg=None,
                        needs_relogin=False,
                    )
                )
                await ws_manager.broadcast({
                    "type": "publish_complete",
                    "data": {
                        "video_id": video_id,
                        "platform": platform,
                        "record_id": rid,
                        "platform_url": result.platform_video_url,
                    },
                })
            else:
                await session.execute(
                    update(PublishRecord).where(PublishRecord.id == rid).values(
                        status=PublishStatus.FAILED,
                        error_msg=result.error_msg,
                        needs_relogin=result.needs_relogin,
                        completed_at=now,
                    )
                )
                await ws_manager.broadcast({
                    "type": "publish_error",
                    "data": {
                        "video_id": video_id,
                        "platform": platform,
                        "record_id": rid,
                        "error": result.error_msg,
                        "needs_relogin": result.needs_relogin,
                    },
                })
            await session.commit()

        return result

    async def auto_publish(
        self,
        video_id: int,
        platforms: Optional[list[str]] = None,
        video_file_path: Optional[str] = None,
        fields_by_platform: Optional[dict[str, PublishFields]] = None,
    ) -> dict[str, PublishResult]:
        """自动发布到多个平台 (顺序执行).

        Args:
            video_id: 内部视频 id
            platforms: 默认两个平台
            video_file_path: 视频文件路径；为 None 时尝试从 DB 推导
            fields_by_platform: 每个平台的填表字段；缺省时调 title_translate 生成
        Returns:
            {platform: PublishResult}
        """
        platforms = platforms or list(self.SUPPORTED_PLATFORMS)
        results: dict[str, PublishResult] = {}

        # 取视频信息 + 默认 fields
        from app.models.video import Video
        async with async_session_factory() as session:
            v = (await session.execute(
                select(Video).where(Video.id == video_id)
            )).scalar_one_or_none()
            if not v:
                return {pf: PublishResult(success=False,
                                          error_msg=f"video {video_id} not found")
                        for pf in platforms}

            if video_file_path is None:
                video_file_path = v.dubbed_filepath or ""

        # 如果 dubbed_filepath 不存在，在工作目录中查找实际视频文件
        if video_file_path and not os.path.exists(video_file_path):
            logger.warning("dubbed_filepath not found on disk: %s", video_file_path)
            # Look for actual video file in the work directory
            from app.core.storage import get_download_dir
            work_dir = os.path.join(get_download_dir(), str(video_id))
            if os.path.isdir(work_dir):
                for f in sorted(os.listdir(work_dir), reverse=True):
                    if f.endswith(".mp4") and f not in ("original.mp4",) and "_subtitled" not in f:
                        candidate = os.path.join(work_dir, f)
                        if os.path.isfile(candidate):
                            video_file_path = candidate
                            logger.info("Resolved video file: %s", video_file_path)
                            break

        if not video_file_path or not os.path.exists(video_file_path):
            for pf in platforms:
                results[pf] = PublishResult(
                    success=False,
                    error_msg=f"video {video_id} 未找到 final.mp4 (dubbed_filepath)",
                )
            return results

        # 生成默认 fields（如未提供）
        if fields_by_platform is None:
            from app.services.publish.title_translate import prepare_publish_fields
            try:
                common_fields = await prepare_publish_fields(video_id)
            except Exception as e:
                logger.error("prepare_publish_fields failed: %s", e)
                common_fields = PublishFields(
                    title=f"video-{video_id}",
                    description="",
                    tags=["搬运", "英语学习", "翻译"],
                )
            fields_by_platform = {pf: common_fields for pf in platforms}

        # 顺序发布（避免同时打开两个 Playwright 浏览器抢资源）
        # 跳过未登录平台（不算失败，只标记 needs_relogin）
        from app.services.platform.manager import get_login_manager
        login_mgr = get_login_manager()
        for pf in platforms:
            # 检查登录态 — 未登录则跳过，不阻塞其他平台
            try:
                state = None
                if is_sau_native(pf):
                    # SAU-native platforms (douyin, bilibili, kuaishou, tencent,
                    # xiaohongshu) use SAU's cookie file at the registry path.
                    account_file = self._resolve_account_file(pf)
                    if account_file and os.path.exists(account_file):
                        state = {"cookies": {"__sau__": True}}  # non-empty sentinel
                else:
                    state = login_mgr.load_storage_state(pf)

                if not state or not state.get("cookies"):
                    logger.info("auto_publish: skip %s (not logged in)", pf)
                    results[pf] = PublishResult(
                        success=False,
                        error_msg=f"未登录 {pf}（已跳过）",
                        needs_relogin=True,
                    )
                    continue
            except Exception as e:
                logger.warning("login state check failed for %s: %s", pf, e)

            try:
                result = await self.publish_to_platform(
                    video_id=video_id,
                    platform=pf,
                    fields=fields_by_platform[pf],
                    video_file_path=video_file_path,
                )
                results[pf] = result
            except Exception as e:
                logger.error("auto_publish %s crashed: %s", pf, e)
                results[pf] = PublishResult(success=False, error_msg=str(e))

        return results


# 模块级单例
_manager: Optional[PublishManager] = None


def get_publish_manager() -> PublishManager:
    global _manager
    if _manager is None:
        _manager = PublishManager()
    return _manager
