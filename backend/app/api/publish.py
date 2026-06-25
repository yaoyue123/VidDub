"""Phase 7 publish API.

路由：
- POST   /api/publish/{video_id}/{platform}       手动触发单平台发布
- POST   /api/publish/{video_id}/auto              自动发布到所有已启用平台
- GET    /api/publish/records                      发布记录列表 (filter: video_id, platform, status)
- GET    /api/publish/records/{record_id}          单条记录详情
- POST   /api/publish/records/{record_id}/retry    重试失败记录
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.publish_record import (
    PublishPlatform,
    PublishRecord,
    PublishStatus,
)
from app.models.video import Video
from app.services.publish.base import PublishFields
from app.services.publish.manager import get_publish_manager

logger = logging.getLogger(__name__)
router = APIRouter()


SUPPORTED_PLATFORMS = {PublishPlatform.DOUYIN, PublishPlatform.BILIBILI, PublishPlatform.IXIGUA}


# ── Schemas ──

class PublishManualBody(BaseModel):
    """手动发布请求 — 所有字段可选，缺失则自动生成."""
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    cover_path: Optional[str] = None
    category_id: Optional[str] = None
    copyright_type: Optional[str] = None
    source_url: Optional[str] = None


class PublishTriggerResponse(BaseModel):
    record_id: int
    video_id: int
    platform: str
    status: str
    platform_url: Optional[str] = None
    error: Optional[str] = None
    needs_relogin: bool = False


class AutoPublishResponse(BaseModel):
    video_id: int
    results: dict[str, PublishTriggerResponse]


class PublishRecordOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    video_id: int
    platform: str
    status: str
    platform_video_url: Optional[str] = None
    title_used: Optional[str] = None
    tags_used: Optional[str] = None
    cover_path: Optional[str] = None
    category_used: Optional[str] = None
    copyright_used: Optional[str] = None
    error_msg: Optional[str] = None
    retry_count: int = 0
    needs_relogin: bool = False
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PublishRecordsResponse(BaseModel):
    items: list[PublishRecordOut]
    total: int


# ── Validation ──

def _check_platform(platform: str) -> None:
    if platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(
            status_code=404,
            detail=f"未知平台: {platform} (支持: {sorted(SUPPORTED_PLATFORMS)})",
        )


async def _ensure_video_ready(db: AsyncSession, video_id: int) -> Video:
    v = (await db.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, detail=f"video {video_id} not found")
    if not v.dubbed_filepath:
        raise HTTPException(409, detail="视频尚未完成配音，无可发布文件")
    return v


# ── Endpoints ──

@router.post("/{video_id}/auto", response_model=AutoPublishResponse)
async def trigger_auto_publish(
    video_id: int,
    db: AsyncSession = Depends(get_db),
):
    """自动发布到所有已启用平台."""
    v = await _ensure_video_ready(db, video_id)

    pm = get_publish_manager()
    results_raw = await pm.auto_publish(
        video_id=video_id,
        video_file_path=v.dubbed_filepath,
    )

    results: dict[str, PublishTriggerResponse] = {}
    for pf, r in results_raw.items():
        # 查 record
        rec = (await db.execute(
            select(PublishRecord)
            .where(PublishRecord.video_id == video_id, PublishRecord.platform == pf)
            .order_by(desc(PublishRecord.id)).limit(1)
        )).scalar_one_or_none()
        results[pf] = PublishTriggerResponse(
            record_id=rec.id if rec else 0,
            video_id=video_id,
            platform=pf,
            status=PublishStatus.PUBLISHED if r.success else PublishStatus.FAILED,
            platform_url=r.platform_video_url,
            error=r.error_msg,
            needs_relogin=r.needs_relogin,
        )

    return AutoPublishResponse(video_id=video_id, results=results)


@router.post("/{video_id}/{platform}", response_model=PublishTriggerResponse)
async def trigger_publish(
    video_id: int,
    platform: str,
    body: Optional[PublishManualBody] = None,
    db: AsyncSession = Depends(get_db),
):
    """手动触发单平台发布 (后台同步执行).

    注意：POST /{video_id}/auto 由独立的 trigger_auto_publish 路由处理，
    FastAPI 按注册顺序匹配，/auto 在 /{platform} 之前注册以避免被捕获。
    """
    _check_platform(platform)
    v = await _ensure_video_ready(db, video_id)

    # 构建 fields
    if body and (body.title or body.tags or body.category_id):
        fields = PublishFields(
            title=body.title or v.title,
            description=body.description or v.description or "",
            tags=body.tags or [],
            cover_path=body.cover_path,
            category_id=body.category_id,
            copyright_type=body.copyright_type or ("repost" if platform == PublishPlatform.IXIGUA else None),
            source_url=body.source_url,
        )
    else:
        # 默认通过 title_translate 生成
        from app.services.publish.title_translate import prepare_publish_fields
        try:
            fields = await prepare_publish_fields(video_id)
        except Exception as e:
            logger.warning("prepare_publish_fields failed: %s", e)
            fields = PublishFields(title=v.title)

    pm = get_publish_manager()
    result = await pm.publish_to_platform(
        video_id=video_id,
        platform=platform,
        fields=fields,
        video_file_path=v.dubbed_filepath,
    )

    # 取最新 record id
    rec = (await db.execute(
        select(PublishRecord)
        .where(PublishRecord.video_id == video_id, PublishRecord.platform == platform)
        .order_by(desc(PublishRecord.id)).limit(1)
    )).scalar_one_or_none()
    rid = rec.id if rec else 0

    return PublishTriggerResponse(
        record_id=rid,
        video_id=video_id,
        platform=platform,
        status=PublishStatus.PUBLISHED if result.success else PublishStatus.FAILED,
        platform_url=result.platform_video_url,
        error=result.error_msg,
        needs_relogin=result.needs_relogin,
    )


@router.get("/records", response_model=PublishRecordsResponse)
async def list_records(
    video_id: Optional[int] = Query(None),
    platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """发布记录列表 (支持过滤)."""
    q = select(PublishRecord).order_by(desc(PublishRecord.id))
    if video_id is not None:
        q = q.where(PublishRecord.video_id == video_id)
    if platform:
        _check_platform(platform)
        q = q.where(PublishRecord.platform == platform)
    if status:
        q = q.where(PublishRecord.status == status)

    # total
    from sqlalchemy import func
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    rows = (await db.execute(q.limit(limit).offset(offset))).scalars().all()
    items = [PublishRecordOut.model_validate(r) for r in rows]
    return PublishRecordsResponse(items=items, total=total)


@router.get("/records/{record_id}", response_model=PublishRecordOut)
async def get_record(record_id: int, db: AsyncSession = Depends(get_db)):
    r = (await db.execute(
        select(PublishRecord).where(PublishRecord.id == record_id)
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, detail=f"record {record_id} not found")
    return PublishRecordOut.model_validate(r)


@router.post("/records/{record_id}/retry", response_model=PublishTriggerResponse)
async def retry_record(record_id: int, db: AsyncSession = Depends(get_db)):
    """重试失败的发布记录."""
    rec = (await db.execute(
        select(PublishRecord).where(PublishRecord.id == record_id)
    )).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, detail=f"record {record_id} not found")
    if rec.status not in (PublishStatus.FAILED, PublishStatus.PUBLISHED):
        raise HTTPException(409, detail=f"记录状态 {rec.status} 不可重试")

    v = (await db.execute(select(Video).where(Video.id == rec.video_id))).scalar_one_or_none()
    if not v or not v.dubbed_filepath:
        raise HTTPException(409, detail="视频文件缺失")

    # 复用原填表字段
    fields = PublishFields(
        title=rec.title_used or v.title,
        description=rec.desc_used or "",
        tags=[t for t in (rec.tags_used or "").split(",") if t.strip()],
        cover_path=rec.cover_path,
        category_id=rec.category_used,
        copyright_type=rec.copyright_used,
        source_url=v.youtube_url if rec.copyright_used == "repost" else None,
    )

    pm = get_publish_manager()
    result = await pm.publish_to_platform(
        video_id=rec.video_id,
        platform=rec.platform,
        fields=fields,
        video_file_path=v.dubbed_filepath,
        record_id=rec.id,
    )

    return PublishTriggerResponse(
        record_id=rec.id,
        video_id=rec.video_id,
        platform=rec.platform,
        status=PublishStatus.PUBLISHED if result.success else PublishStatus.FAILED,
        platform_url=result.platform_video_url,
        error=result.error_msg,
        needs_relogin=result.needs_relogin,
    )
