from typing import Optional

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlparse

from app.core.database import get_db
from app.core.config import settings
from app.models.video import Video
from app.models.task import Task
from app.models.config import Config
from app.models.enums import VideoStatus, TaskType, TaskStatus
from app.schemas import VideoResponse, VideoListResponse, VideoStatusUpdate
from app.services.youtube import YoutubeService
from app.services.config_seeder import DEFAULT_CONFIGS

router = APIRouter()


class CreateVideoRequest(BaseModel):
    youtube_url: str = Field(..., description="YouTube 视频链接")
    channel: str = ""
    title: str = ""


# CR-03: SSRF 防护 — youtube_url 只允许 YouTube 主域名
YOUTUBE_HOSTS = frozenset({
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
})


def _validate_youtube_url(url: str) -> None:
    """校验 youtube_url 是否指向 YouTube 主域名（防 SSRF）."""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=422,
            detail="youtube_url 必须是 http(s):// 开头",
        )
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=422,
            detail=f"不支持的 URL scheme: {parsed.scheme!r}",
        )
    host = (parsed.hostname or "").lower()
    if not host:
        raise HTTPException(
            status_code=422,
            detail="youtube_url 缺少 hostname",
        )
    if host not in YOUTUBE_HOSTS:
        raise HTTPException(
            status_code=422,
            detail=f"URL 必须指向 YouTube (允许: {sorted(YOUTUBE_HOSTS)})，"
                   f"当前 host: {host!r}",
        )


@router.post("", response_model=VideoResponse, status_code=201)
async def create_video(body: CreateVideoRequest, db: AsyncSession = Depends(get_db)):
    """Add a video by URL. Extracts metadata via yt-dlp if possible."""
    import re

    url = str(body.youtube_url).strip()
    _validate_youtube_url(url)  # CR-03: SSRF 防护

    # Parse YouTube ID from URL
    patterns = [
        r"(?:v=|/v/|youtu\.be/)([\w-]{11})",
        r"(?:embed/)([\w-]{11})",
        r"(?:shorts/)([\w-]{11})",
    ]
    youtube_id = None
    for pat in patterns:
        m = re.search(pat, body.youtube_url)
        if m:
            youtube_id = m.group(1)
            break

    if not youtube_id:
        raise HTTPException(status_code=400, detail="无法解析 YouTube 视频 ID")

    # Check duplicate
    existing = (await db.execute(
        select(Video).where(Video.youtube_id == youtube_id)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="该视频已存在")

    # Try to extract metadata
    title = body.title or f"YouTube Video ({youtube_id})"
    channel = body.channel or ""
    duration = None
    view_count = None
    like_count = None
    thumbnail_url = None
    description = ""

    try:
        config_result = await db.execute(select(Config))
        configs = {c.key: c.value for c in config_result.scalars().all()}
        download_dir = configs.get("download_dir", "./downloads")
        max_res = int(configs.get("max_resolution", "1080"))
        service = YoutubeService(download_dir=download_dir, max_resolution=max_res)
        info = await service.get_video_info(body.youtube_url)
        if info:
            title = info.get("title") or title
            channel = info.get("channel") or channel
            duration = info.get("duration")
            view_count = info.get("view_count")
            like_count = info.get("like_count")
            thumbnail_url = info.get("thumbnail_url")
            description = info.get("description") or ""
    except Exception as e:
        # Metadata extraction is best-effort
        pass

    video = Video(
        youtube_url=body.youtube_url,
        youtube_id=youtube_id,
        title=title,
        channel=channel,
        duration=duration,
        view_count=view_count,
        like_count=like_count,
        thumbnail_url=thumbnail_url,
        description=description,
        status=VideoStatus.PENDING,
    )
    db.add(video)
    await db.flush()
    await db.refresh(video)
    return video


@router.get("", response_model=VideoListResponse)
async def list_videos(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(Video)
    count_query = select(func.count(Video.id))

    if status:
        query = query.where(Video.status == status)
        count_query = count_query.where(Video.status == status)
    if search:
        like_pattern = f"%{search}%"
        query = query.where(Video.title.ilike(like_pattern))
        count_query = count_query.where(Video.title.ilike(like_pattern))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Video.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    videos = result.scalars().all()

    return VideoListResponse(total=total, items=list(videos))


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(video_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.patch("/{video_id}/status", response_model=VideoResponse)
async def update_video_status(
    video_id: int,
    body: VideoStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    video.status = body.status
    await db.flush()
    await db.refresh(video)
    return video


@router.get("/{video_id}/download/dubbed")
async def download_dubbed_video(video_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if not video.dubbed_filepath or not os.path.exists(video.dubbed_filepath):
        raise HTTPException(status_code=404, detail="Dubbed video file not found")
    filename = os.path.basename(video.dubbed_filepath)
    return FileResponse(video.dubbed_filepath, filename=filename, media_type="video/mp4")


@router.delete("/{video_id}", status_code=204)
async def delete_video(video_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    await db.delete(video)
    await db.flush()
