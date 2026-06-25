"""Phase 9: ChannelScanner — APScheduler 定时扫描频道，自动入库 + 创建下载任务.

设计 (per D9-01, D9-05, D9-06, D9-07, Claude discretion notes):
- AsyncIOScheduler 集成 FastAPI 生命周期
- 内存 jobstore（重启时从 DB 重建）
- 多频道并行扫描，限制 max_concurrent
- 每频道一个 job，按 channel.scan_interval_hours 调度
- scan_once: 调 YoutubeService.get_channel_videos() → 过滤 → 去重 → 批量创建 Video + 首个 download Task
- 每次 scan 写 ScanLog (found/added/error)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.database import async_session_factory
from app.models.channel import Channel
from app.models.enums import TaskType, TaskStatus, VideoStatus
from app.models.scan_log import ScanLog
from app.models.task import Task
from app.models.video import Video
from app.services.youtube import YoutubeService

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """scan_once 返回值."""
    channel_id: int
    found_count: int
    added_count: int
    error_msg: Optional[str] = None


class ChannelScanner:
    """APScheduler 驱动的频道扫描器."""

    JOB_ID_PREFIX = "channel_scan_"

    def __init__(
        self,
        youtube_service: Optional[YoutubeService] = None,
        max_concurrent: int = 3,
        default_interval_hours: int = 6,
    ):
        self._yt = youtube_service or YoutubeService()
        self._max_concurrent = max_concurrent
        self._default_interval_hours = default_interval_hours
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._semaphore = asyncio.Semaphore(max_concurrent)

    # ── 生命周期 ──

    async def start(self) -> None:
        """启动扫描器：注册所有 enabled channels 的 job."""
        if self._scheduler is not None:
            logger.warning("ChannelScanner already started")
            return

        self._scheduler = AsyncIOScheduler()
        self._scheduler.start()

        async with async_session_factory() as session:
            result = await session.execute(
                select(Channel).where(Channel.enabled.is_(True))
            )
            channels = result.scalars().all()

        for ch in channels:
            self._register_job(ch)

        logger.info(
            "ChannelScanner started: %d channels registered (max_concurrent=%d)",
            len(channels), self._max_concurrent,
        )

    async def stop(self) -> None:
        """关闭扫描器."""
        if self._scheduler is None:
            return
        self._scheduler.shutdown(wait=False)
        self._scheduler = None
        logger.info("ChannelScanner stopped")

    # ── Job 管理 ──

    def _register_job(self, channel: Channel) -> None:
        """为单个频道注册 APScheduler 作业."""
        if self._scheduler is None:
            logger.warning("Scheduler not started, cannot register channel %d", channel.id)
            return
        job_id = f"{self.JOB_ID_PREFIX}{channel.id}"
        interval = channel.scan_interval_hours or self._default_interval_hours
        trigger = IntervalTrigger(hours=interval)
        self._scheduler.add_job(
            self._scan_job_wrapper,
            trigger=trigger,
            args=[channel.id],
            id=job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.debug("Registered job %s (interval=%dh)", job_id, interval)

    def reschedule_channel(self, channel: Channel) -> None:
        """更新某频道的扫描间隔 (运行时调用)."""
        if self._scheduler is None:
            logger.warning("Scheduler not started, cannot reschedule channel %d", channel.id)
            return
        if not channel.enabled:
            self.remove_channel(channel.id)
            return
        self._register_job(channel)

    def remove_channel(self, channel_id: int) -> None:
        """移除某频道的作业."""
        if self._scheduler is None:
            return
        job_id = f"{self.JOB_ID_PREFIX}{channel_id}"
        try:
            self._scheduler.remove_job(job_id)
            logger.debug("Removed job %s", job_id)
        except Exception:
            pass

    async def _scan_job_wrapper(self, channel_id: int) -> None:
        """APScheduler 调用的入口：捕获异常，记录 ScanLog."""
        try:
            await self.scan_once(channel_id)
        except Exception as e:
            logger.error("Channel %d scan job failed: %s", channel_id, e, exc_info=True)
            # 兜底写 ScanLog
            try:
                async with async_session_factory() as session:
                    session.add(ScanLog(
                        channel_id=channel_id,
                        found_count=0, added_count=0,
                        error_msg=f"扫描异常: {e}",
                    ))
                    await session.commit()
            except Exception:
                pass

    # ── 扫描 ──

    async def scan_once(self, channel_id: int) -> ScanResult:
        """执行单次扫描: 拉视频 → 过滤 → 去重 → 入库 + 创建下载任务 → 写 ScanLog.

        Returns:
            ScanResult
        """
        async with self._semaphore:
            return await self._scan_once_impl(channel_id)

    async def _scan_once_impl(self, channel_id: int) -> ScanResult:
        # 1. 加载频道
        async with async_session_factory() as session:
            ch_result = await session.execute(select(Channel).where(Channel.id == channel_id))
            channel = ch_result.scalar_one_or_none()

        if channel is None:
            return ScanResult(channel_id=channel_id, found_count=0, added_count=0,
                              error_msg="频道不存在")
        if not channel.enabled:
            return ScanResult(channel_id=channel_id, found_count=0, added_count=0,
                              error_msg="频道已禁用")

        # 2. 拉取频道视频列表 (Phase 2 YoutubeService.get_channel_videos)
        try:
            videos = await self._yt.get_channel_videos(channel.url, max_results=50)
        except Exception as e:
            logger.error("Channel %d fetch failed: %s", channel_id, e)
            await self._write_scan_log(channel_id, 0, 0, f"拉取失败: {e}")
            return ScanResult(channel_id=channel_id, found_count=0, added_count=0,
                              error_msg=str(e))

        found_count = len(videos)

        # 3. 应用过滤
        filtered = self._apply_filters(videos, channel)

        # 4. 去重 + 批量入库
        added = await self._bulk_add_videos(filtered, channel.id)

        # 5. 更新 channel.last_scanned_at
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            await session.execute(
                update(Channel).where(Channel.id == channel_id).values(last_scanned_at=now)
            )
            await session.commit()

        # 6. 写 ScanLog
        await self._write_scan_log(channel_id, found_count, added, None)

        logger.info(
            "Channel %d scanned: found=%d, filtered=%d, added=%d",
            channel_id, found_count, len(filtered), added,
        )
        return ScanResult(
            channel_id=channel_id,
            found_count=found_count,
            added_count=added,
            error_msg=None,
        )

    def _apply_filters(
        self,
        videos: list[dict],
        channel: Channel,
    ) -> list[dict]:
        """按频道过滤条件筛选 (min_views / duration 范围)."""
        out: list[dict] = []
        for v in videos:
            views = v.get("view_count")
            duration = v.get("duration")
            if channel.filter_min_views is not None:
                if views is None or views < channel.filter_min_views:
                    continue
            if channel.filter_min_duration_sec is not None:
                if duration is None or duration < channel.filter_min_duration_sec:
                    continue
            if channel.filter_max_duration_sec is not None:
                if duration is None or duration > channel.filter_max_duration_sec:
                    continue
            out.append(v)
        return out

    async def _bulk_add_videos(
        self,
        videos: list[dict],
        channel_id: int,
    ) -> int:
        """去重 + 批量插入 Video + 首个 download Task. 返回成功添加数."""
        if not videos:
            return 0

        # 取出所有 youtube_id
        youtube_ids = [v.get("youtube_id") for v in videos if v.get("youtube_id")]
        if not youtube_ids:
            return 0

        # 查询已存在的 youtube_id
        async with async_session_factory() as session:
            existing_result = await session.execute(
                select(Video.youtube_id).where(Video.youtube_id.in_(youtube_ids))
            )
            existing_ids = {row[0] for row in existing_result.all()}

        added = 0
        async with async_session_factory() as session:
            for v in videos:
                yt_id = v.get("youtube_id")
                if not yt_id or yt_id in existing_ids:
                    continue

                webpage_url = v.get("webpage_url") or f"https://www.youtube.com/watch?v={yt_id}"
                video = Video(
                    youtube_url=webpage_url,
                    youtube_id=yt_id,
                    title=v.get("title") or f"(no title) {yt_id}",
                    channel=v.get("channel") or "",
                    duration=v.get("duration"),
                    view_count=v.get("view_count"),
                    like_count=v.get("like_count"),
                    comment_count=v.get("comment_count"),
                    thumbnail_url=v.get("thumbnail_url"),
                    description=v.get("description") or "",
                    status=VideoStatus.PENDING,
                    channel_id=channel_id,
                    source="channel",
                )
                session.add(video)
                try:
                    await session.flush()
                except IntegrityError:
                    # 并发插入竞态 — 回滚当前 video 但继续下一个
                    await session.rollback()
                    continue

                # 创建首个 download Task
                task = Task(
                    video_id=video.id,
                    type=TaskType.DOWNLOAD,
                    status=TaskStatus.PENDING,
                    progress=0.0,
                    message="等待频道扫描下载...",
                )
                session.add(task)
                added += 1
                existing_ids.add(yt_id)

            await session.commit()

        return added

    async def _write_scan_log(
        self,
        channel_id: int,
        found_count: int,
        added_count: int,
        error_msg: Optional[str],
    ) -> None:
        try:
            async with async_session_factory() as session:
                session.add(ScanLog(
                    channel_id=channel_id,
                    found_count=found_count,
                    added_count=added_count,
                    error_msg=error_msg,
                ))
                await session.commit()
        except Exception as e:
            logger.error("Failed to write ScanLog: %s", e)


# ── Module-level singleton (lazy) ──

_scanner: Optional[ChannelScanner] = None


def get_channel_scanner() -> ChannelScanner:
    """获取全局 ChannelScanner 实例."""
    global _scanner
    if _scanner is None:
        _scanner = ChannelScanner()
    return _scanner


def set_channel_scanner(scanner: Optional[ChannelScanner]) -> None:
    """测试/启动时注入实例."""
    global _scanner
    _scanner = scanner
