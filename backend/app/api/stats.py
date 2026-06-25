"""Stats API: dashboard and overview statistics.

Phase 5 新增：
- GET /api/stats/dashboard — Dashboard 专用聚合数据 (per B5)
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.video import Video
from app.models.task import Task
from app.models.enums import VideoStatus, TaskStatus
from app.schemas import StatsResponse

router = APIRouter()


# ── Dashboard Schemas ──

class DashboardRecentTask(BaseModel):
    """Dashboard 最近任务卡片."""
    video_id: int
    title: str
    status: str
    current_step: str
    progress_pct: float
    error_msg: Optional[str] = None
    created_at: str
    final_url: Optional[str] = None
    thumbnail_url: Optional[str] = None


class DashboardResponse(BaseModel):
    """Dashboard 聚合数据 (B5)."""
    today_count: int
    success_rate: float
    avg_duration_sec: Optional[float]
    api_calls_estimate: int
    recent_tasks: list[DashboardRecentTask]
    failed_tasks: list[DashboardRecentTask]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_today(ts: Optional[datetime]) -> bool:
    if ts is None:
        return False
    now = _utcnow()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.date() == now.date()


def _compute_avg_duration(rows: list[Task]) -> Optional[float]:
    """对已完成的 download→compose 任务链计算平均耗时 (秒)."""
    by_video: dict[int, list[datetime]] = {}
    for t in rows:
        if t.status != TaskStatus.COMPLETED:
            continue
        if t.created_at is None or t.updated_at is None:
            continue
        by_video.setdefault(t.video_id, []).extend(
            [t.created_at, t.updated_at]
        )
    durations: list[float] = []
    for ts_list in by_video.values():
        if len(ts_list) < 2:
            continue
        delta = (max(ts_list) - min(ts_list)).total_seconds()
        if delta > 0:
            durations.append(delta)
    if not durations:
        return None
    return sum(durations) / len(durations)


# ── Endpoints ──

@router.get("", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    total_videos_result = await db.execute(select(func.count(Video.id)))
    total_videos = total_videos_result.scalar() or 0

    status_counts_result = await db.execute(
        select(Video.status, func.count(Video.id)).group_by(Video.status)
    )
    status_counts = dict(status_counts_result.all())

    total_tasks_result = await db.execute(select(func.count(Task.id)))
    total_tasks = total_tasks_result.scalar() or 0

    return StatsResponse(
        total_videos=total_videos,
        status_counts=status_counts,
        total_tasks=total_tasks,
    )


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    """Dashboard 聚合数据 (B5).

    - today_count: 今日新建的 Video 数（按 created_at UTC date 过滤）
    - success_rate: 已完成 / (已完成 + 失败) 百分比
    - avg_duration_sec: 已完成任务的平均耗时（按 task 时间戳估算）
    - api_calls_estimate: today_count × 估算的 API 调用次数（粗略：每视频 30 次 TTS + 1 次 Chat）
    - recent_tasks: 最近 5 个非 failed 视频（含状态/进度）
    - failed_tasks: 最近 5 个 failed 视频
    """
    # 1. 所有视频
    all_videos_result = await db.execute(
        select(Video).order_by(Video.created_at.desc())
    )
    all_videos: list[Video] = list(all_videos_result.scalars().all())

    today_count = sum(1 for v in all_videos if _is_today(v.created_at))

    completed = [v for v in all_videos if v.status == VideoStatus.COMPLETED]
    failed = [v for v in all_videos if v.status == VideoStatus.FAILED]
    denom = len(completed) + len(failed)
    success_rate = round(len(completed) / denom * 100, 1) if denom > 0 else 0.0

    # 2. 所有任务用于平均耗时估算
    all_tasks_result = await db.execute(select(Task))
    all_tasks: list[Task] = list(all_tasks_result.scalars().all())
    avg_duration = _compute_avg_duration(all_tasks)

    # 3. API 调用估算：粗略模型 — 每个今日新增视频 30 TTS + 1 Chat + 1 STT ≈ 32
    api_calls_estimate = today_count * 32

    # 4. 拉每个视频的最新任务以构造 recent/failed 列表
    async def _latest_task_for(vid: int) -> Optional[Task]:
        r = await db.execute(
            select(Task).where(Task.video_id == vid)
            .order_by(Task.created_at.desc()).limit(1)
        )
        return r.scalar_one_or_none()

    def _to_recent(v: Video, t: Optional[Task]) -> DashboardRecentTask:
        return DashboardRecentTask(
            video_id=v.id,
            title=v.title,
            status=v.status,
            current_step=t.type if t else "idle",
            progress_pct=float(t.progress) if t else 0.0,
            error_msg=t.error_msg if t else None,
            created_at=str(v.created_at) if v.created_at else "",
            final_url=(
                f"/api/dub/{v.id}/download" if v.status == VideoStatus.COMPLETED else None
            ),
            thumbnail_url=v.thumbnail_url,
        )

    # recent: 排除 failed，按 created_at desc 前 5
    recent_candidates = [v for v in all_videos if v.status != VideoStatus.FAILED][:5]
    recent_tasks: list[DashboardRecentTask] = []
    for v in recent_candidates:
        t = await _latest_task_for(v.id)
        recent_tasks.append(_to_recent(v, t))

    failed_recent = failed[:5]
    failed_task_list: list[DashboardRecentTask] = []
    for v in failed_recent:
        t = await _latest_task_for(v.id)
        failed_task_list.append(_to_recent(v, t))

    return DashboardResponse(
        today_count=today_count,
        success_rate=success_rate,
        avg_duration_sec=avg_duration,
        api_calls_estimate=api_calls_estimate,
        recent_tasks=recent_tasks,
        failed_tasks=failed_task_list,
    )
