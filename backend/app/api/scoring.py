"""Scoring API — video scoring and history.

POST /api/scoring/batch     — score multiple videos by YouTube ID or channel
GET  /api/scoring/video/{id} — get score for single video
GET  /api/scoring/history    — list recent scores
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.video_score import VideoScore

logger = logging.getLogger(__name__)
router = APIRouter()


class BatchScoreRequest(BaseModel):
    youtube_ids: Optional[list[str]] = None
    channel_url: Optional[str] = None
    max_results: int = 20


class BatchScoreResponse(BaseModel):
    items: list[dict]
    total: int


class ScoreHistoryResponse(BaseModel):
    items: list[dict]
    total: int


@router.post("/batch")
async def score_batch(
    body: BatchScoreRequest,
    db: AsyncSession = Depends(get_db),
):
    """Score multiple videos and return sorted results.

    Accepts a list of youtube_ids or a channel URL.
    Uses YouTube API if key is configured, otherwise yt-dlp fallback.
    """
    from app.services.scoring.metrics import fetch_batch_metrics
    from app.services.scoring.scorer import score_video
    from app.services.scoring.classifier import classify_video_content

    # Resolve YouTube IDs
    youtube_ids: list[str] = []
    if body.youtube_ids:
        youtube_ids = body.youtube_ids[:50]  # rate limit
    elif body.channel_url:
        youtube_ids = await _resolve_channel_videos(
            body.channel_url, body.max_results,
        )

    if not youtube_ids:
        raise HTTPException(
            status_code=400,
            detail="No youtube_ids or channel_url provided",
        )

    # Fetch metrics for all videos
    api_key = _get_youtube_api_key()
    metrics_map = await fetch_batch_metrics(youtube_ids, api_key=api_key)

    # Score each video
    results = []
    for yid in youtube_ids:
        metrics = metrics_map.get(yid, {})
        if "error" in metrics:
            continue

        # Classify content category (async, per-video)
        try:
            from app.services.siliconflow.client import get_async_client
            async with get_async_client(timeout=30.0) as client:
                category = await classify_video_content(
                    metrics.get("title", ""),
                    description="",
                    tags=metrics.get("tags", []),
                    channel_id=metrics.get("channel_id", ""),
                    client=client,
                )
        except Exception as e:
            logger.debug("Classification skipped for %s: %s", yid, e)
            category = "other"

        scored = score_video(metrics, category=category)

        # Persist to DB
        existing = (
            await db.execute(
                select(VideoScore).where(VideoScore.youtube_id == yid),
            )
        ).scalar_one_or_none()

        if existing:
            # Update existing score
            for field, value in scored.items():
                if field in ("weights_used", "raw_metrics"):
                    continue
                setattr(existing, field, value)
            existing.weights_used = scored["weights_used"]
            existing.raw_metrics = scored["raw_metrics"]
            existing.scored_at = datetime.now(timezone.utc)
        else:
            db.add(VideoScore(
                youtube_id=yid,
                title=metrics.get("title", ""),
                channel_name=metrics.get("channel_name", ""),
                channel_id=metrics.get("channel_id", ""),
                thumbnail_url=metrics.get("thumbnail_url", ""),
                virality_score=scored["virality_score"],
                translation_score=scored["translation_score"],
                quality_score=scored["quality_score"],
                market_score=scored["market_score"],
                cost_score=scored["cost_score"],
                composite_score=scored["composite_score"],
                weights_used=scored["weights_used"],
                raw_metrics=scored["raw_metrics"],
                scored_at=datetime.now(timezone.utc),
                scorer_version="1.0",
                category=category,
            ))

        results.append(_to_score_dict(scored, metrics))

    await db.commit()

    # Sort by composite score descending
    results.sort(key=lambda x: x["composite_score"], reverse=True)

    return BatchScoreResponse(items=results, total=len(results))


@router.get("/video/{youtube_id}")
async def get_score(
    youtube_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the stored score for a single video."""
    result = await db.execute(
        select(VideoScore).where(VideoScore.youtube_id == youtube_id),
    )
    score = result.scalar_one_or_none()
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")

    return _to_response(score)


@router.get("/history")
async def get_score_history(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List recently scored videos."""
    result = await db.execute(
        select(VideoScore)
        .order_by(VideoScore.scored_at.desc())
        .offset(offset)
        .limit(limit),
    )
    scores = result.scalars().all()

    total_result = await db.execute(select(VideoScore))
    total = len(total_result.scalars().all())

    return ScoreHistoryResponse(
        items=[_to_response(s) for s in scores],
        total=total,
    )


# ── Helpers ──

def _get_youtube_api_key() -> Optional[str]:
    """Get YouTube Data API key from settings or environment."""
    key = getattr(settings, "youtube_api_key", "") or ""
    return key.strip() or None


async def _resolve_channel_videos(
    channel_url: str, max_results: int,
) -> list[str]:
    """Resolve a channel URL to recent video IDs via yt-dlp."""
    proc = await __import__("asyncio").create_subprocess_exec(
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        "--playlist-end", str(max_results),
        channel_url,
        stdout=__import__("asyncio").subprocess.PIPE,
        stderr=__import__("asyncio").subprocess.PIPE,
    )

    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        raise HTTPException(
            status_code=400,
            detail="Failed to resolve channel URL",
        )

    ids = []
    for line in stdout.decode("utf-8").strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            yid = data.get("id") or data.get("webpage_url", "").split("v=")[-1]
            if yid:
                ids.append(yid)
        except json.JSONDecodeError:
            continue

    return ids


def _to_score_dict(scored: dict, metrics: dict) -> dict:
    """Build API response dict from scorer output."""
    return {
        "youtube_id": metrics.get("youtube_id", ""),
        "title": metrics.get("title", ""),
        "channel_name": metrics.get("channel_name", ""),
        "thumbnail_url": metrics.get("thumbnail_url", ""),
        "composite_score": scored["composite_score"],
        "virality_score": scored["virality_score"],
        "translation_score": scored["translation_score"],
        "quality_score": scored["quality_score"],
        "market_score": scored["market_score"],
        "cost_score": scored["cost_score"],
        "category": scored.get("category"),
        "view_count": metrics.get("view_count", 0),
        "like_count": metrics.get("like_count", 0),
        "duration_sec": metrics.get("duration_sec", 0),
    }


def _to_response(score: VideoScore) -> dict:
    """Convert VideoScore ORM object to API response dict."""
    return {
        "id": score.id,
        "youtube_id": score.youtube_id,
        "title": score.title,
        "channel_name": score.channel_name,
        "thumbnail_url": score.thumbnail_url,
        "composite_score": score.composite_score,
        "virality_score": score.virality_score,
        "translation_score": score.translation_score,
        "quality_score": score.quality_score,
        "market_score": score.market_score,
        "cost_score": score.cost_score,
        "category": score.category,
        "scored_at": score.scored_at.isoformat() if score.scored_at else None,
        "scorer_version": score.scorer_version,
    }
