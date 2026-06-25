"""
Video discovery API: search YouTube, scan channels, trigger downloads.

All discovery operations use yt-dlp and run via executor threads.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, async_session_factory
from app.core.websocket import manager as ws_manager
from app.models.video import Video
from app.models.task import Task
from app.models.config import Config
from app.services.youtube import YoutubeService
from app.schemas import VideoResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request / Response models ──

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="搜索关键词")
    max_results: int = Field(20, ge=1, le=100)
    min_views: Optional[int] = Field(None, ge=0)
    min_duration: Optional[int] = Field(None, ge=0, description="最短时长（秒）")
    max_duration: Optional[int] = Field(None, ge=0, description="最长时长（秒）")


class ChannelScanRequest(BaseModel):
    channel_url: str = Field(..., description="YouTube 频道 URL")
    max_results: int = Field(50, ge=1, le=200)


class VideoInfoRequest(BaseModel):
    url: str = Field(..., description="YouTube 视频 URL")


class DiscoveryItem(BaseModel):
    youtube_id: str
    title: str
    channel: str
    channel_url: str = ""
    duration: Optional[int] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    thumbnail_url: Optional[str] = None
    webpage_url: str = ""


class DiscoveryResponse(BaseModel):
    items: list[DiscoveryItem]


class DownloadRequest(BaseModel):
    video_id: int = Field(..., description="数据库中的视频 ID")


class AddVideoRequest(BaseModel):
    """Add discovered videos to the local database."""
    youtube_id: str
    youtube_url: str
    title: str
    channel: str
    duration: Optional[int] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    thumbnail_url: Optional[str] = None
    description: Optional[str] = None


class BatchAddResponse(BaseModel):
    added: list[VideoResponse]
    skipped: list[str]


# ── Helpers ──

def _get_yt_service_from_db(configs: dict[str, str]) -> YoutubeService:
    """Build YoutubeService from config dict."""
    download_dir = configs.get("download_dir", "./downloads")
    max_res = int(configs.get("max_resolution", "1080"))
    return YoutubeService(download_dir=download_dir, max_resolution=max_res)


async def _get_config_map(db: AsyncSession) -> dict[str, str]:
    """Load config as flat dict."""
    result = await db.execute(select(Config))
    configs = result.scalars().all()
    return {c.key: c.value for c in configs}


# ── Routes ──

@router.post("/search", response_model=DiscoveryResponse)
async def search_youtube(
    body: SearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Search YouTube videos using yt-dlp."""
    configs = await _get_config_map(db)
    service = _get_yt_service_from_db(configs)

    try:
        results = await service.search(body.query, max_results=body.max_results)
    except Exception as e:
        logger.error("Search failed: %s", e)
        raise HTTPException(status_code=502, detail=f"YouTube 搜索失败: {str(e)}")

    # Apply client-side filters
    filtered = []
    for item in results:
        if body.min_views and (item.get("view_count") or 0) < body.min_views:
            continue
        if body.min_duration and (item.get("duration") or 0) < body.min_duration:
            continue
        if body.max_duration and (item.get("duration") or 0) > body.max_duration:
            continue
        filtered.append(item)

    return DiscoveryResponse(items=[DiscoveryItem(**i) for i in filtered])


@router.post("/channel", response_model=DiscoveryResponse)
async def scan_channel(
    body: ChannelScanRequest,
    db: AsyncSession = Depends(get_db),
):
    """Scan a YouTube channel for videos."""
    configs = await _get_config_map(db)
    service = _get_yt_service_from_db(configs)

    try:
        results = await service.get_channel_videos(body.channel_url, max_results=body.max_results)
    except Exception as e:
        logger.error("Channel scan failed: %s", e)
        raise HTTPException(status_code=502, detail=f"频道扫描失败: {str(e)}")

    return DiscoveryResponse(items=[DiscoveryItem(**i) for i in results])


@router.post("/info", response_model=DiscoveryItem)
async def get_video_info(
    body: VideoInfoRequest,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed info for a single video."""
    configs = await _get_config_map(db)
    service = _get_yt_service_from_db(configs)

    try:
        info = await service.get_video_info(body.url)
    except Exception as e:
        logger.error("Get video info failed: %s", e)
        raise HTTPException(status_code=502, detail=f"获取视频信息失败: {str(e)}")

    if not info:
        raise HTTPException(status_code=404, detail="视频未找到")

    return DiscoveryItem(**info)


@router.post("/add", response_model=BatchAddResponse)
async def add_discovered_videos(
    body: list[AddVideoRequest],
    db: AsyncSession = Depends(get_db),
):
    """Batch add discovered videos to the local database.

    Skips videos that already exist (by youtube_id).
    """
    added = []
    skipped = []

    for item in body:
        # Check for duplicates
        existing = (await db.execute(
            select(Video).where(Video.youtube_id == item.youtube_id)
        )).scalar_one_or_none()
        if existing:
            skipped.append(item.youtube_id)
            continue

        video = Video(
            youtube_url=item.youtube_url,
            youtube_id=item.youtube_id,
            title=item.title,
            channel=item.channel,
            duration=item.duration,
            view_count=item.view_count,
            like_count=item.like_count,
            thumbnail_url=item.thumbnail_url,
            description=item.description,
            status="pending",
        )
        db.add(video)
        added.append(video)

    await db.flush()

    # Refresh to get IDs
    for v in added:
        await db.refresh(v)

    return BatchAddResponse(
        added=[VideoResponse.model_validate(v) for v in added],
        skipped=skipped,
    )


@router.post("/download", response_model=dict)
async def trigger_download(
    body: DownloadRequest,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a download task for an existing video."""
    # Verify video exists
    result = await db.execute(select(Video).where(Video.id == body.video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.status not in ("pending", "failed"):
        raise HTTPException(status_code=400, detail=f"视频当前状态不允许下载: {video.status}")

    # Create download task
    task = Task(
        video_id=video.id,
        type="download",
        status="pending",
        progress=0.0,
        message="等待下载...",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    # Update video status
    video.status = "pending"

    return {"task_id": task.id, "video_id": video.id, "status": "queued"}
