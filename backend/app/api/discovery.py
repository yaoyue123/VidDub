"""
Video discovery API: search YouTube, scan channels, trigger downloads.

All discovery operations use yt-dlp and run via executor threads.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, async_session_factory
from app.core.storage import get_download_dir
from app.core.websocket import manager as ws_manager
from app.models.video import Video
from app.models.task import Task
from app.models.config import Config
from app.models.enums import VideoStatus, TaskType, TaskStatus
from app.services.youtube import YoutubeService
from app.services.discovery_scanner import get_discovery_scanner
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
    download_dir = get_download_dir()
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
            status=VideoStatus.PENDING,
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

    if video.status not in (VideoStatus.PENDING, VideoStatus.FAILED):
        raise HTTPException(status_code=400, detail=f"视频当前状态不允许下载: {video.status}")

    # Create download task
    task = Task(
        video_id=video.id,
        type=TaskType.DOWNLOAD,
        status=TaskStatus.PENDING,
        progress=0.0,
        message="等待下载...",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    # Update video status
    video.status = VideoStatus.PENDING

    return {"task_id": task.id, "video_id": video.id, "status": "queued"}


# ── Phase 14: Discovery source management ──

class DiscoverySourceCreate(BaseModel):
    type: str  # channel | keyword | category | trending
    source_value: str
    label: str
    scan_interval_hours: int = 24
    max_results_per_scan: int = 20
    filter_min_views: Optional[int] = Field(None, ge=0)
    filter_max_views: Optional[int] = Field(None, ge=0)
    filter_min_duration_sec: Optional[int] = Field(None, ge=0)
    filter_max_duration_sec: Optional[int] = Field(None, ge=0)
    filter_published_within_hours: Optional[int] = Field(None, ge=1)


class DiscoverySourceUpdate(BaseModel):
    label: Optional[str] = None
    enabled: Optional[bool] = None
    scan_interval_hours: Optional[int] = None
    max_results_per_scan: Optional[int] = None
    filter_min_views: Optional[int] = Field(None, ge=0)
    filter_max_views: Optional[int] = Field(None, ge=0)
    filter_min_duration_sec: Optional[int] = Field(None, ge=0)
    filter_max_duration_sec: Optional[int] = Field(None, ge=0)
    filter_published_within_hours: Optional[int] = Field(None, ge=1)


class DiscoverySourceResponse(BaseModel):
    id: int
    type: str
    source_value: str
    label: str
    enabled: bool
    last_scanned_at: Optional[datetime] = None
    scan_interval_hours: int
    max_results_per_scan: int
    filter_min_views: Optional[int] = None
    filter_max_views: Optional[int] = None
    filter_min_duration_sec: Optional[int] = None
    filter_max_duration_sec: Optional[int] = None
    filter_published_within_hours: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SaveSearchAsSourceRequest(BaseModel):
    """Save search criteria as a new tracked DiscoverySource."""
    query: str = Field(..., min_length=1, description="搜索关键词")
    label: str = Field(..., max_length=128, description="显示名称")
    max_results: int = Field(20, ge=1, le=100)
    min_views: Optional[int] = Field(None, ge=0)
    max_views: Optional[int] = Field(None, ge=0)
    min_duration_sec: Optional[int] = Field(None, ge=0)
    max_duration_sec: Optional[int] = Field(None, ge=0)
    published_within_hours: Optional[int] = Field(None, ge=1)
    scan_interval_hours: int = Field(24, ge=1, le=720)


@router.get("/sources")
async def list_discovery_sources(db: AsyncSession = Depends(get_db)):
    """List all discovery sources with filter fields."""
    from app.models.discovery import DiscoverySource
    result = await db.execute(
        select(DiscoverySource).order_by(DiscoverySource.created_at.desc()),
    )
    sources = result.scalars().all()
    return {
        "items": [DiscoverySourceResponse.model_validate(s) for s in sources],
        "total": len(sources),
    }


@router.post("/sources", response_model=DiscoverySourceResponse, status_code=201)
async def create_discovery_source(
    body: DiscoverySourceCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a new discovery source with optional filter conditions."""
    from app.models.discovery import DiscoverySource
    source = DiscoverySource(
        type=body.type,
        source_value=body.source_value,
        label=body.label,
        scan_interval_hours=body.scan_interval_hours,
        max_results_per_scan=body.max_results_per_scan,
        filter_min_views=body.filter_min_views,
        filter_max_views=body.filter_max_views,
        filter_min_duration_sec=body.filter_min_duration_sec,
        filter_max_duration_sec=body.filter_max_duration_sec,
        filter_published_within_hours=body.filter_published_within_hours,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return DiscoverySourceResponse.model_validate(source)


@router.post("/sources/from-search", response_model=DiscoverySourceResponse, status_code=201)
async def save_search_as_source(
    body: SaveSearchAsSourceRequest,
    db: AsyncSession = Depends(get_db),
):
    """Save search criteria as a new DiscoverySource for auto-scanning."""
    from app.models.discovery import DiscoverySource

    source = DiscoverySource(
        type="keyword",
        source_value=body.query,
        label=body.label,
        max_results_per_scan=body.max_results,
        scan_interval_hours=body.scan_interval_hours,
        filter_min_views=body.min_views,
        filter_max_views=body.max_views,
        filter_min_duration_sec=body.min_duration_sec,
        filter_max_duration_sec=body.max_duration_sec,
        filter_published_within_hours=body.published_within_hours,
    )
    db.add(source)
    await db.flush()
    await db.refresh(source)
    return DiscoverySourceResponse.model_validate(source)


@router.put("/sources/{source_id}", response_model=DiscoverySourceResponse)
async def update_discovery_source(
    source_id: int,
    body: DiscoverySourceUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a discovery source including filter conditions."""
    from app.models.discovery import DiscoverySource
    source = await db.get(DiscoverySource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    update_data = body.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(source, k, v)

    await db.commit()
    await db.refresh(source)
    return DiscoverySourceResponse.model_validate(source)


@router.delete("/sources/{source_id}")
async def delete_discovery_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a discovery source and its results."""
    from app.models.discovery import DiscoverySource
    source = await db.get(DiscoverySource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    await db.delete(source)
    await db.commit()
    return {"ok": True}


@router.post("/sources/{source_id}/scan")
async def scan_discovery_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a manual scan of a discovery source using DiscoveryScanner."""
    from app.models.discovery import DiscoverySource
    source = await db.get(DiscoverySource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    scanner = get_discovery_scanner()
    result = await scanner.scan_once(source_id)

    return {
        "source_id": source_id,
        "found_count": result.found_count,
        "added_count": result.added_count,
        "status": result.status,
        "error_msg": result.error_msg,
    }


@router.get("/sources/{source_id}/scan-logs")
async def list_discovery_scan_logs(
    source_id: int,
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List scan logs for a discovery source."""
    from app.models.discovery_scan_log import DiscoveryScanLog
    from app.models.discovery import DiscoverySource

    source = await db.get(DiscoverySource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    query = (
        select(DiscoveryScanLog)
        .where(DiscoveryScanLog.source_id == source_id)
        .order_by(DiscoveryScanLog.scanned_at.desc())
        .limit(limit)
    )
    items = (await db.execute(query)).scalars().all()
    return {"items": items, "total": len(items)}


@router.get("/results")
async def list_discovery_results(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List discovery results with optional status filter."""
    from app.models.discovery import DiscoveryResult

    query = select(DiscoveryResult).order_by(
        DiscoveryResult.discovered_at.desc(),
    )
    if status:
        query = query.where(DiscoveryResult.status == status)

    total = len((await db.execute(select(DiscoveryResult))).scalars().all())
    result = await db.execute(query.offset(offset).limit(limit))
    items = result.scalars().all()

    return {"items": items, "total": total}


@router.put("/results/{result_id}/ignore")
async def ignore_discovery_result(
    result_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Mark a discovery result as ignored."""
    from app.models.discovery import DiscoveryResult
    from sqlalchemy import update as sql_update

    result = await db.get(DiscoveryResult, result_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    await db.execute(
        sql_update(DiscoveryResult)
        .where(DiscoveryResult.id == result_id)
        .values(status="ignored"),
    )
    await db.commit()
    return {"ok": True}


@router.post("/results/{result_id}/dub")
async def dub_discovery_result(
    result_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Create a dub task from a discovered video."""
    from app.models.discovery import DiscoveryResult
    from app.models.enums import TaskType, TaskStatus, VideoStatus
    from sqlalchemy import update as sql_update

    result = await db.get(DiscoveryResult, result_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    # Create or find the Video record
    youtube_url = f"https://www.youtube.com/watch?v={result.youtube_id}"
    existing = (
        await db.execute(
            select(Video).where(Video.youtube_id == result.youtube_id),
        )
    ).scalar_one_or_none()

    if existing:
        video = existing
    else:
        video = Video(
            youtube_url=youtube_url,
            youtube_id=result.youtube_id,
            title=result.title,
            channel=result.channel_name,
            status=VideoStatus.PENDING,
            source="discovery",
        )
        db.add(video)
        await db.flush()

    # Create download task
    task = Task(
        video_id=video.id,
        type=TaskType.DOWNLOAD,
        status=TaskStatus.PENDING,
        progress=0.0,
        message="从发现页创建，等待下载...",
    )
    db.add(task)

    # Update discovery result status
    await db.execute(
        sql_update(DiscoveryResult)
        .where(DiscoveryResult.id == result_id)
        .values(status="dubbed", video_id=video.id),
    )
    await db.commit()

    return {"task_id": task.id, "video_id": video.id, "status": "queued"}


@router.get("/channels")
async def list_tracked_channels(db: AsyncSession = Depends(get_db)):
    """List tracked channel sources with stats."""
    from app.models.discovery import DiscoverySource
    result = await db.execute(
        select(DiscoverySource).where(
            DiscoverySource.type == "channel",
            DiscoverySource.enabled == True,
        ),
    )
    sources = result.scalars().all()

    channels = []
    for s in sources:
        channels.append({
            "id": s.id,
            "label": s.label,
            "source_value": s.source_value,
            "last_scanned_at": s.last_scanned_at.isoformat() if s.last_scanned_at else None,
            "scan_interval_hours": s.scan_interval_hours,
        })

    return {"items": channels, "total": len(channels)}
