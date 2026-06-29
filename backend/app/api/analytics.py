"""Phase 17: Analytics API — performance tracking and reports."""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.performance_log import PerformanceLog
from app.models.video_score import VideoScore
from app.schemas import (
    PerformanceLogResponse,
    PerformanceDetailResponse,
    TopPerformerResponse,
    PerformanceReportResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class PerformanceLogRequest(BaseModel):
    video_id: int
    youtube_id: str
    platform: str
    platform_views: int
    platform_likes: int = 0
    platform_comments: int = 0
    platform_shares: Optional[int] = None
    platform_url: Optional[str] = None
    fetch_method: str = "manual"


@router.post("/performance", response_model=PerformanceLogResponse)
async def log_performance_endpoint(
    body: PerformanceLogRequest,
    db: AsyncSession = Depends(get_db),
):
    """Record platform performance for a dubbed video."""
    from app.services.scoring.performance import log_performance
    try:
        log = await log_performance(
            video_id=body.video_id,
            youtube_id=body.youtube_id,
            platform=body.platform,
            platform_views=body.platform_views,
            platform_likes=body.platform_likes,
            platform_comments=body.platform_comments,
            platform_shares=body.platform_shares,
            platform_url=body.platform_url,
            fetch_method=body.fetch_method,
        )
    except Exception as e:
        logger.error("记录平台表现失败: %s", e)
        raise HTTPException(status_code=500, detail="记录平台表现失败，请稍后重试")

    return PerformanceLogResponse(
        id=log.id,
        video_id=log.video_id,
        platform=log.platform,
        predicted_score=log.predicted_score,
        actual_score=log.actual_score,
        score_accuracy=log.score_accuracy,
    )


@router.get("/performance/{video_id}", response_model=PerformanceDetailResponse)
async def get_performance(video_id: int, db: AsyncSession = Depends(get_db)):
    """Get performance data for a specific video."""
    from app.services.scoring.performance import compare_predicted_vs_actual

    result = await db.execute(
        select(PerformanceLog).where(
            PerformanceLog.video_id == video_id,
        ).order_by(PerformanceLog.logged_at.desc()),
    )
    logs = result.scalars().all()

    if not logs:
        raise HTTPException(status_code=404, detail="No performance data")

    return PerformanceDetailResponse(
        video_id=video_id,
        logs=[
            PerformanceLogResponse(
                id=log.id,
                video_id=log.video_id,
                platform=log.platform,
                platform_views=log.platform_views,
                platform_likes=log.platform_likes,
                predicted_score=log.predicted_score,
                actual_score=log.actual_score,
                score_accuracy=log.score_accuracy,
                logged_at=log.logged_at.isoformat() if log.logged_at else None,
            )
            for log in logs
        ],
    )


@router.get("/score-accuracy")
async def get_score_accuracy(days: int = Query(default=30)):
    """Get overall scoring accuracy statistics."""
    from app.services.scoring.performance import get_score_accuracy_stats
    return await get_score_accuracy_stats(days=days)


@router.get("/top-performers", response_model=TopPerformerResponse)
async def get_top_performers(limit: int = Query(default=10, le=50)):
    """Get historically best-performing dubbed videos."""
    from app.services.scoring.performance import get_top_performers
    return TopPerformerResponse(items=await get_top_performers(limit=limit))


@router.get("/monthly-report", response_model=PerformanceReportResponse)
async def get_monthly_report(
    year: int = Query(default=2026),
    month: int = Query(default=6),
    db: AsyncSession = Depends(get_db),
):
    """Generate a monthly performance report."""
    from app.services.scoring.performance import get_score_accuracy_stats

    accuracy = await get_score_accuracy_stats()

    # Count videos scored this month
    from sqlalchemy import func, extract
    score_count = await db.execute(
        select(func.count(VideoScore.id)).where(
            extract("year", VideoScore.scored_at) == year,
            extract("month", VideoScore.scored_at) == month,
        ),
    )
    total_scored = score_count.scalar() or 0

    perf_count = await db.execute(
        select(func.count(PerformanceLog.id)).where(
            extract("year", PerformanceLog.logged_at) == year,
            extract("month", PerformanceLog.logged_at) == month,
        ),
    )
    total_performance_logs = perf_count.scalar() or 0

    # Top performers
    top = (
        await db.execute(
            select(PerformanceLog)
            .order_by(PerformanceLog.platform_views.desc())
            .limit(5),
        )
    ).scalars().all()

    return PerformanceReportResponse(
        period=f"{year}-{month:02d}",
        summary={
            "videos_scored": total_scored,
            "performance_logs": total_performance_logs,
            "avg_score_accuracy": accuracy["avg_accuracy"],
            "over_estimate_ratio": accuracy["over_estimate_ratio"],
        },
        top_performers=[
            {
                "video_id": t.video_id,
                "youtube_id": t.youtube_id,
                "platform": t.platform,
                "views": t.platform_views,
                "predicted": t.predicted_score,
                "actual": t.actual_score,
            }
            for t in top
        ],
        accuracy_interpretation=accuracy["interpretation"],
    )
