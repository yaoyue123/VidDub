"""Performance tracking — compare predicted scores vs actual results."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, func

from app.core.database import async_session_factory
from app.models.performance_log import PerformanceLog
from app.models.video_score import VideoScore

logger = logging.getLogger(__name__)


async def log_performance(
    video_id: int,
    youtube_id: str,
    platform: str,
    platform_views: int,
    platform_likes: int,
    platform_comments: int,
    *,
    platform_shares: Optional[int] = None,
    platform_url: Optional[str] = None,
    fetch_method: str = "manual",
) -> PerformanceLog:
    """Record actual platform performance for a dubbed video."""
    predicted = await _get_predicted_score(youtube_id)
    actual = calculate_actual_score(
        platform_views, platform_likes, platform_comments,
        platform=platform,
    )
    accuracy = abs(predicted - actual)

    async with async_session_factory() as session:
        log = PerformanceLog(
            video_id=video_id,
            youtube_id=youtube_id,
            platform=platform,
            platform_views=platform_views,
            platform_likes=platform_likes,
            platform_comments=platform_comments,
            platform_shares=platform_shares,
            platform_url=platform_url,
            predicted_score=predicted,
            actual_score=actual,
            score_accuracy=accuracy,
            logged_at=datetime.now(timezone.utc),
            fetch_method=fetch_method,
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
    return log


def calculate_actual_score(
    views: int,
    likes: int,
    comments: int,
    *,
    platform: str = "bilibili",
) -> float:
    """Normalize platform performance to 0-100 scale.

    Different platforms have different scales:
    - Bilibili: views heavily favored, coins/favorites matter
    """
    if platform == "bilibili":
        # Bilibili: views dominate, likes/coins/favorites are secondary
        score = 0.0
        if views >= 1_000_000:
            score += 60.0
        elif views >= 100_000:
            score += 50.0
        elif views >= 10_000:
            score += 35.0
        elif views >= 1_000:
            score += 20.0
        elif views > 0:
            score += 5.0

        # Engagement (likes + comments relative to views)
        if views > 0:
            engagement = (likes + comments * 2) / views
            engagement = min(engagement, 0.15)
            score += (engagement / 0.15) * 40.0

        return min(100.0, score)

    else:
        # Generic platform scoring
        score = 0.0
        if views >= 500_000:
            score += 50.0
        elif views >= 50_000:
            score += 35.0
        elif views >= 5_000:
            score += 20.0
        elif views > 0:
            score += 5.0

        if views > 0:
            engagement = (likes + comments) / views
            engagement = min(engagement, 0.10)
            score += (engagement / 0.10) * 50.0

        return min(100.0, score)


async def compare_predicted_vs_actual(
    youtube_id: str,
) -> Optional[dict[str, Any]]:
    """Compare predicted score vs actual performance for a video."""
    async with async_session_factory() as session:
        logs = (
            await session.execute(
                select(PerformanceLog)
                .where(PerformanceLog.youtube_id == youtube_id)
                .order_by(PerformanceLog.logged_at.desc()),
            )
        ).scalars().all()

    if not logs:
        return None

    log = logs[0]
    return {
        "youtube_id": youtube_id,
        "predicted_score": log.predicted_score,
        "actual_score": log.actual_score,
        "accuracy": log.score_accuracy,
        "platform": log.platform,
        "platform_views": log.platform_views,
        "platform_likes": log.platform_likes,
        "logged_at": log.logged_at.isoformat() if log.logged_at else None,
    }


async def get_score_accuracy_stats(days: int = 30) -> dict[str, Any]:
    """Calculate overall scoring accuracy statistics."""
    async with async_session_factory() as session:
        # Average accuracy
        avg_result = await session.execute(
            select(func.avg(PerformanceLog.score_accuracy))
        )
        avg_accuracy = avg_result.scalar() or 0.0

        # Count
        count_result = await session.execute(
            select(func.count(PerformanceLog.id))
        )
        total_logs = count_result.scalar() or 0

        # Over/under estimation bias
        over_result = await session.execute(
            select(func.count(PerformanceLog.id)).where(
                PerformanceLog.predicted_score >
                PerformanceLog.actual_score,
            )
        )
        over_count = over_result.scalar() or 0

    over_ratio = over_count / max(total_logs, 1)

    return {
        "total_logs": total_logs,
        "avg_accuracy": round(avg_accuracy, 1),
        "over_estimate_ratio": round(over_ratio, 2),
        "interpretation": (
            "Accuracy = |predicted - actual|. Lower is better. "
            f"Over-estimate ratio {over_ratio:.0%}: "
            f"{'模型倾向于高估视频表现' if over_ratio > 0.6 else '模型倾向于低估视频表现' if over_ratio < 0.4 else '预测偏差均衡'}"
        ),
    }


async def get_top_performers(limit: int = 10) -> list[dict[str, Any]]:
    """Get historically best-performing dubbed videos."""
    async with async_session_factory() as session:
        logs = (
            await session.execute(
                select(PerformanceLog)
                .order_by(PerformanceLog.platform_views.desc())
                .limit(limit),
            )
        ).scalars().all()

    return [
        {
            "video_id": log.video_id,
            "youtube_id": log.youtube_id,
            "platform": log.platform,
            "platform_views": log.platform_views,
            "platform_likes": log.platform_likes,
            "predicted_score": log.predicted_score,
            "actual_score": log.actual_score,
            "logged_at": log.logged_at.isoformat() if log.logged_at else None,
        }
        for log in logs
    ]


async def _get_predicted_score(youtube_id: str) -> float:
    """Get the predicted composite score from VideoScore table."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(VideoScore).where(VideoScore.youtube_id == youtube_id),
        )
        score = result.scalar_one_or_none()
        return score.composite_score if score else 0.0
