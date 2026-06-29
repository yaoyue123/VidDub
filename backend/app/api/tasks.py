import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

from app.core.database import get_db
from app.models.task import Task
from app.models.video import Video
from app.models.subtitle import Subtitle
from app.models.enums import TaskStatus
from app.schemas import TaskResponse, TaskListResponse, VideoResponse

router = APIRouter()


# ── Schemas ──

class CreateTaskRequest(BaseModel):
    video_id: int
    type: str


class BatchActionRequest(BaseModel):
    """D9-08: 批量操作."""
    action: str  # pause | resume | retry | delete
    ids: list[int]


class BatchActionResponse(BaseModel):
    success_count: int
    failed_count: int
    errors: list[dict]


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: Optional[str] = Query(None, alias="type"),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(Task).join(Video, Task.video_id == Video.id, isouter=True)
    count_query = select(func.count(Task.id)).join(
        Video, Task.video_id == Video.id, isouter=True,
    )

    if type:
        query = query.where(Task.type == type)
        count_query = count_query.where(Task.type == type)
    if status:
        query = query.where(Task.status == status)
        count_query = count_query.where(Task.status == status)
    # F5: source / date range 筛选
    if source:
        query = query.where(Video.source == source)
        count_query = count_query.where(Video.source == source)
    if date_from:
        query = query.where(Task.created_at >= date_from)
        count_query = count_query.where(Task.created_at >= date_from)
    if date_to:
        query = query.where(Task.created_at <= date_to)
        count_query = count_query.where(Task.created_at <= date_to)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Task.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    # Eager-load video relationship so we can populate video_title/thumbnail
    query = query.options(selectinload(Task.video))
    result = await db.execute(query)
    tasks = result.scalars().all()

    # Build response items with video metadata merged in
    items = [_task_to_response(t) for t in tasks]

    return TaskListResponse(total=total, items=items)


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    body: CreateTaskRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new task (e.g. transcribe)."""
    # Verify video exists
    v_result = await db.execute(select(Video).where(Video.id == body.video_id))
    if not v_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Video not found")

    task = Task(
        video_id=body.video_id,
        type=body.type,
        status=TaskStatus.PENDING,
        progress=0.0,
        message="等待处理...",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


def _task_to_response(task: Task) -> TaskResponse:
    """Convert Task ORM object to TaskResponse, including video metadata."""
    v = task.video if hasattr(task, 'video') else None
    return TaskResponse(
        id=task.id,
        video_id=task.video_id,
        type=task.type,
        status=task.status,
        progress=task.progress,
        message=task.message,
        error_msg=task.error_msg,
        video_title=v.title if v else None,
        video_thumbnail_url=v.thumbnail_url if v else None,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Task).where(Task.id == task_id).options(selectinload(Task.video))
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_response(task)


@router.post("/{task_id}/retry", response_model=TaskResponse)
async def retry_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Task).where(Task.id == task_id).options(selectinload(Task.video))
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = TaskStatus.PENDING
    task.progress = 0.0
    task.error_msg = None
    await db.flush()
    await db.refresh(task)
    return _task_to_response(task)


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Task).where(Task.id == task_id).options(selectinload(Task.video))
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = TaskStatus.CANCELLED
    await db.flush()
    await db.refresh(task)
    return _task_to_response(task)


# ── Phase 9 B11: 批量操作 ──

@router.post("/batch", response_model=BatchActionResponse)
async def batch_tasks(
    body: BatchActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """批量 pause / resume / retry / delete.

    action:
        pause  → 将 pending 任务标记为 cancelled
        resume → 将 cancelled/pending 任务标记为 pending
        retry  → 将 failed 任务标记为 pending
        delete → 软删除关联 videos (videos.deleted_at = now)
    """
    if not body.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    if body.action not in ("pause", "resume", "retry", "delete"):
        raise HTTPException(status_code=400, detail=f"未知 action: {body.action}")

    success = 0
    failed = 0
    errors: list[dict] = []

    for tid in body.ids:
        try:
            result = await db.execute(select(Task).where(Task.id == tid))
            task = result.scalar_one_or_none()
            if not task:
                failed += 1
                errors.append({"id": tid, "error": "Task not found"})
                continue

            if body.action == "pause":
                if task.status == TaskStatus.PENDING:
                    task.status = TaskStatus.CANCELLED
                    task.message = "批量暂停"
                else:
                    failed += 1
                    errors.append({"id": tid, "error": f"当前状态 {task.status} 不可暂停"})
                    continue
            elif body.action == "resume":
                if task.status in (TaskStatus.CANCELLED, TaskStatus.PENDING):
                    task.status = TaskStatus.PENDING
                    task.message = "批量恢复"
                else:
                    failed += 1
                    errors.append({"id": tid, "error": f"当前状态 {task.status} 不可恢复"})
                    continue
            elif body.action == "retry":
                if task.status == TaskStatus.FAILED:
                    task.status = TaskStatus.PENDING
                    task.progress = 0.0
                    task.error_msg = None
                    task.message = "批量重试"
                else:
                    failed += 1
                    errors.append({"id": tid, "error": f"当前状态 {task.status} 不可重试"})
                    continue
            elif body.action == "delete":
                # 物理删除 Video 及所有关联数据 (Tasks, Subtitles, PublishRecords)
                v_result = await db.execute(select(Video).where(Video.id == task.video_id))
                v = v_result.scalar_one_or_none()
                if v:
                    video_id = v.id
                    # 显式删除关联表（避免 ORM flush 设 NULL 的问题）
                    from app.models.subtitle import Subtitle
                    from app.models.publish_record import PublishRecord
                    await db.execute(sql_delete(PublishRecord).where(PublishRecord.video_id == video_id))
                    await db.execute(sql_delete(Subtitle).where(Subtitle.video_id == video_id))
                    await db.execute(sql_delete(Task).where(Task.video_id == video_id))
                    await db.execute(sql_delete(Video).where(Video.id == video_id))
                    await db.flush()
                    _cleanup_video_files(video_id)

            success += 1
        except Exception as e:
            failed += 1
            errors.append({"id": tid, "error": str(e)})

    await db.flush()
    return BatchActionResponse(success_count=success, failed_count=failed, errors=errors)


# ── v3.2: Task Detail (视频简介 + 字幕) ──

class SubtitleItem(BaseModel):
    """单条字幕摘要（用于详情弹窗）."""
    id: int
    language: str
    source: str
    content: Optional[str] = None
    filepath: Optional[str] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class TaskDetailResponse(BaseModel):
    """任务详情 — 包含视频元数据 + 所有字幕."""
    task: TaskResponse
    video: VideoResponse
    subtitles: list[SubtitleItem]


@router.get("/{task_id}/detail", response_model=TaskDetailResponse)
async def get_task_detail(task_id: int, db: AsyncSession = Depends(get_db)):
    """获取任务详情：视频简介 + 原始/翻译字幕."""
    result = await db.execute(
        select(Task).where(Task.id == task_id).options(selectinload(Task.video))
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    video = task.video

    # 拉取该视频的所有字幕
    sub_result = await db.execute(
        select(Subtitle).where(Subtitle.video_id == task.video_id)
        .order_by(Subtitle.language, Subtitle.created_at.desc())
    )
    subtitles = sub_result.scalars().all()

    # v3.2: All subtitle data unified in DB (original + translated)
    items: list[SubtitleItem] = [
        SubtitleItem(
            id=s.id,
            language=s.language,
            source=s.source,
            content=s.content,
            filepath=s.filepath,
            created_at=str(s.created_at) if s.created_at else None,
        ) for s in subtitles
    ]

    return TaskDetailResponse(
        task=_task_to_response(task),
        video=VideoResponse.model_validate(video) if video else None,
        subtitles=items,
    )


# ── Helpers ──

def _cleanup_video_files(video_id: int) -> None:
    """删除视频磁盘文件 (downloads/{video_id}/ 目录)."""
    import shutil
    from pathlib import Path as _Path
    work_dir = _Path(__file__).resolve().parent.parent.parent / "downloads" / str(video_id)
    if work_dir.exists():
        try:
            shutil.rmtree(work_dir)
            logger.info("Cleaned up disk files for video %d: %s", video_id, work_dir)
        except OSError as e:
            logger.warning("Failed to clean up video %d files: %s", video_id, e)
