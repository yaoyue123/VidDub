"""Phase 9: 任务/视频导出 CSV/JSON (D9-10).

Endpoints:
- GET /api/export/tasks?format=csv|json&filters=...
  Streams CSV or JSON of tasks matching filters.
"""
import csv
import io
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.task import Task
from app.models.video import Video

router = APIRouter()


# D9-10: 导出字段
EXPORT_COLUMNS = [
    "task_id", "video_id", "youtube_id", "title",
    "status", "type", "progress",
    "created_at", "updated_at", "completed_at",
    "error_msg",
]


async def _query_tasks(
    db: AsyncSession,
    status: Optional[str] = None,
    type: Optional[str] = None,
    source: Optional[str] = None,
    include_deleted: bool = False,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 1000,
) -> list[dict]:
    """统一查询逻辑，CSV / JSON 共用."""
    query = (
        select(Task, Video)
        .join(Video, Task.video_id == Video.id, isouter=True)
    )

    if not include_deleted:
        query = query.where(Video.deleted_at.is_(None))
    if status:
        query = query.where(Task.status == status)
    if type:
        query = query.where(Task.type == type)
    if source:
        query = query.where(Video.source == source)
    if date_from:
        query = query.where(Task.created_at >= date_from)
    if date_to:
        query = query.where(Task.created_at <= date_to)

    query = query.order_by(Task.created_at.desc()).limit(limit)
    result = await db.execute(query)

    rows: list[dict] = []
    for task, video in result.all():
        completed_at = None
        if task.status == "completed":
            completed_at = task.updated_at.isoformat() if task.updated_at else None
        rows.append({
            "task_id": task.id,
            "video_id": task.video_id,
            "youtube_id": video.youtube_id if video else "",
            "title": video.title if video else "",
            "status": task.status,
            "type": task.type,
            "progress": task.progress,
            "created_at": task.created_at.isoformat() if task.created_at else "",
            "updated_at": task.updated_at.isoformat() if task.updated_at else "",
            "completed_at": completed_at or "",
            "error_msg": task.error_msg or "",
        })
    return rows


@router.get("/tasks")
async def export_tasks(
    format: str = Query("csv", pattern="^(csv|json)$"),
    status: Optional[str] = Query(None),
    type: Optional[str] = Query(None, alias="type"),
    source: Optional[str] = Query(None),
    include_deleted: bool = Query(False),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
):
    rows = await _query_tasks(
        db, status=status, type=type, source=source,
        include_deleted=include_deleted,
        date_from=date_from, date_to=date_to,
        limit=limit,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if format == "json":
        content = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
        return StreamingResponse(
            io.BytesIO(content),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="tasks_export_{timestamp}.json"'
            },
        )

    # CSV (D9-10) — 使用 stdlib csv 流式输出
    def iter_csv():
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        for row in rows:
            writer.writerow(row)
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    return StreamingResponse(
        iter_csv(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="tasks_export_{timestamp}.csv"'
        },
    )
