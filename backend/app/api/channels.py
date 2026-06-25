"""Phase 9: Channels CRUD + scan-now + scan-logs (D9-03, D9-07).

Endpoints:
- GET    /api/channels                 列表
- POST   /api/channels                 创建
- GET    /api/channels/{id}            详情
- PUT    /api/channels/{id}            更新
- DELETE /api/channels/{id}            删除
- POST   /api/channels/{id}/scan-now   立即扫描
- GET    /api/channels/{id}/scan-logs  扫描历史
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.channel import Channel
from app.models.scan_log import ScanLog
from app.services.channel_scanner import get_channel_scanner

router = APIRouter()


# ── Schemas ──

class ChannelBase(BaseModel):
    name: str = Field(..., max_length=128)
    url: str = Field(..., max_length=512)
    enabled: bool = True
    scan_interval_hours: int = Field(6, ge=1, le=720)
    filter_min_views: Optional[int] = None
    filter_max_duration_sec: Optional[int] = None
    filter_min_duration_sec: Optional[int] = None
    auto_publish: bool = False


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    url: Optional[str] = Field(None, max_length=512)
    enabled: Optional[bool] = None
    scan_interval_hours: Optional[int] = Field(None, ge=1, le=720)
    filter_min_views: Optional[int] = None
    filter_max_duration_sec: Optional[int] = None
    filter_min_duration_sec: Optional[int] = None
    auto_publish: Optional[bool] = None


class ChannelResponse(ChannelBase):
    id: int
    last_scanned_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChannelListResponse(BaseModel):
    total: int
    items: list[ChannelResponse]


class ScanLogResponse(BaseModel):
    id: int
    channel_id: int
    scanned_at: datetime
    found_count: int
    added_count: int
    error_msg: Optional[str] = None

    model_config = {"from_attributes": True}


class ScanLogListResponse(BaseModel):
    items: list[ScanLogResponse]


class ScanNowResponse(BaseModel):
    channel_id: int
    found_count: int
    added_count: int
    error_msg: Optional[str] = None


# ── Routes ──

@router.get("", response_model=ChannelListResponse)
async def list_channels(
    enabled: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(Channel)
    count_query = select(func.count(Channel.id))
    if enabled is not None:
        query = query.where(Channel.enabled.is_(enabled))
        count_query = count_query.where(Channel.enabled.is_(enabled))

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(Channel.created_at.desc())
    items = (await db.execute(query)).scalars().all()
    return ChannelListResponse(total=total, items=list(items))


@router.post("", response_model=ChannelResponse, status_code=201)
async def create_channel(body: ChannelCreate, db: AsyncSession = Depends(get_db)):
    # URL 唯一性检查
    existing = await db.execute(select(Channel).where(Channel.url == body.url))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该频道 URL 已存在")

    channel = Channel(**body.model_dump())
    db.add(channel)
    await db.flush()
    await db.refresh(channel)

    # 注册到扫描器
    try:
        scanner = get_channel_scanner()
        scanner.reschedule_channel(channel)
    except Exception:
        pass

    return channel


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: int, db: AsyncSession = Depends(get_db)):
    channel = (await db.execute(select(Channel).where(Channel.id == channel_id))).scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


@router.put("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: int,
    body: ChannelUpdate,
    db: AsyncSession = Depends(get_db),
):
    channel = (await db.execute(select(Channel).where(Channel.id == channel_id))).scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    update_data = body.model_dump(exclude_unset=True)
    # URL 唯一性检查
    if "url" in update_data and update_data["url"] != channel.url:
        existing = await db.execute(
            select(Channel).where(Channel.url == update_data["url"], Channel.id != channel_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="该频道 URL 已存在")

    for k, v in update_data.items():
        setattr(channel, k, v)

    await db.flush()
    await db.refresh(channel)

    # 重新调度
    try:
        scanner = get_channel_scanner()
        scanner.reschedule_channel(channel)
    except Exception:
        pass

    return channel


@router.delete("/{channel_id}", status_code=204)
async def delete_channel(channel_id: int, db: AsyncSession = Depends(get_db)):
    channel = (await db.execute(select(Channel).where(Channel.id == channel_id))).scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    await db.delete(channel)
    await db.flush()

    # 从扫描器移除
    try:
        scanner = get_channel_scanner()
        scanner.remove_channel(channel_id)
    except Exception:
        pass


@router.post("/{channel_id}/scan-now", response_model=ScanNowResponse)
async def scan_now(channel_id: int, db: AsyncSession = Depends(get_db)):
    """立即触发扫描（不等下一个 interval）."""
    channel = (await db.execute(select(Channel).where(Channel.id == channel_id))).scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    scanner = get_channel_scanner()
    result = await scanner.scan_once(channel_id)
    return ScanNowResponse(
        channel_id=result.channel_id,
        found_count=result.found_count,
        added_count=result.added_count,
        error_msg=result.error_msg,
    )


@router.get("/{channel_id}/scan-logs", response_model=ScanLogListResponse)
async def list_scan_logs(
    channel_id: int,
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    # 验证 channel 存在
    channel = (await db.execute(select(Channel).where(Channel.id == channel_id))).scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    query = (
        select(ScanLog)
        .where(ScanLog.channel_id == channel_id)
        .order_by(ScanLog.scanned_at.desc())
        .limit(limit)
    )
    items = (await db.execute(query)).scalars().all()
    return ScanLogListResponse(items=list(items))
