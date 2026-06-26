"""Scoring API — video scoring and history.

POST /api/scoring/batch     — score multiple videos by YouTube ID or channel
GET  /api/scoring/video/{id} — get score for single video
GET  /api/scoring/history    — list recent scores
"""

import asyncio
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


# ── Auto-discover: one-shot seeding + trending + scoring ──


@router.get("/discover")
async def auto_discover(
    refresh: bool = Query(default=False),
    limit: int = Query(default=30, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Auto-discover trending videos with scoring + recommendation rationale.

    On first call (or refresh=true):
    1. Seeds default discovery sources if none exist
    2. Seeds rule templates if needed
    3. Scrapes trending videos from YouTube across 4 categories
    4. Scores each video (5-dimension model)
    5. Deduplicates against previously processed videos
    6. Returns ranked results with rationale per video

    Cached results served on subsequent calls (refresh=false).
    """
    from app.services.scoring.rule_engine import seed_rule_templates
    from app.services.scoring.discovery import scrape_trending
    from app.services.scoring.scorer import score_video
    from app.services.scoring.metrics import fetch_video_metrics
    from app.services.scoring.classifier import classify_video_content
    from app.services.siliconflow.client import get_async_client
    from app.models.discovery import DiscoverySource, DiscoveryResult

    # 1. Seed defaults (idempotent)
    await _seed_default_sources(db)
    await seed_rule_templates()

    # 2. If not refreshing, serve cached results from DB
    if not refresh:
        result = await db.execute(
            select(VideoScore)
            .order_by(VideoScore.composite_score.desc())
            .limit(limit),
        )
        cached = result.scalars().all()
        if cached:
            return {
                "items": [_to_discover_item(s) for s in cached],
                "total": len(cached),
                "source": "cache",
            }

    # 3. Fetch + score trending videos
    logger.info("Auto-discover: scraping trending videos...")
    trending = await scrape_trending(max_per_category=10)

    if not trending:
        # Fallback: use curated popular channels
        trending = await _curated_fallback(db)

    # 4. Score each video
    scored_items = []
    sem = __import__("asyncio").Semaphore(3)

    async def _score_one(video: dict):
        async with sem:
            yid = video.get("youtube_id", "")
            if not yid:
                return

            # Deduplicate
            existing = (
                await db.execute(
                    select(VideoScore).where(VideoScore.youtube_id == yid),
                )
            ).scalar_one_or_none()
            if existing:
                scored_items.append(_to_discover_item(existing))
                return

            # Fetch full metrics
            try:
                metrics = await fetch_video_metrics(yid)
            except Exception:
                metrics = video  # Use what we have from trending

            if not metrics.get("title"):
                return

            # Classify
            category = "other"
            try:
                async with get_async_client(timeout=15.0) as client:
                    category = await classify_video_content(
                        metrics.get("title", video.get("title", "")),
                        tags=metrics.get("tags", []),
                        channel_id=metrics.get("channel_id", ""),
                        client=client,
                    )
            except Exception:
                pass

            # Score
            scored = score_video(metrics, category=category)

            # Persist
            vs = VideoScore(
                youtube_id=yid,
                title=metrics.get("title", video.get("title", "")),
                channel_name=metrics.get("channel_name", video.get("channel_name", "")),
                channel_id=metrics.get("channel_id", video.get("channel_id", "")),
                thumbnail_url=metrics.get("thumbnail_url", video.get("thumbnail_url", "")),
                virality_score=scored["virality_score"],
                translation_score=scored["translation_score"],
                quality_score=scored["quality_score"],
                market_score=scored["market_score"],
                cost_score=scored["cost_score"],
                composite_score=scored["composite_score"],
                weights_used=scored["weights_used"],
                raw_metrics=scored["raw_metrics"],
                scored_at=datetime.now(timezone.utc),
                category=category,
            )
            db.add(vs)
            scored_items.append(_to_discover_item(vs))

    # Process trending videos in parallel batches
    __import__("asyncio").get_event_loop()
    tasks = [asyncio.create_task(_score_one(v)) for v in trending]
    await asyncio.gather(*tasks, return_exceptions=True)

    await db.commit()

    # Sort by composite score desc
    scored_items.sort(key=lambda x: x["composite_score"], reverse=True)

    return {
        "items": scored_items[:limit],
        "total": len(scored_items),
        "source": "fresh",
    }


def _to_discover_item(vs: VideoScore) -> dict:
    """Convert VideoScore to discover API item with recommendation rationale."""
    return {
        "youtube_id": vs.youtube_id,
        "title": vs.title,
        "channel_name": vs.channel_name,
        "thumbnail_url": vs.thumbnail_url,
        "composite_score": vs.composite_score,
        "virality_score": vs.virality_score,
        "translation_score": vs.translation_score,
        "quality_score": vs.quality_score,
        "market_score": vs.market_score,
        "cost_score": vs.cost_score,
        "category": vs.category,
        "rationale": _build_rationale(vs),
        "scored_at": vs.scored_at.isoformat() if vs.scored_at else None,
    }


def _build_rationale(vs: VideoScore) -> str:
    """Build a human-readable recommendation reason from scores."""
    scores = {
        "virality": vs.virality_score,
        "translation": vs.translation_score,
    }
    reasons = []
    if vs.virality_score >= 70:
        reasons.append("传播力强，播放量和互动率高")
    elif vs.virality_score >= 40:
        reasons.append("有一定传播潜力")
    if vs.translation_score >= 70:
        reasons.append("适合中文配音翻译")
    elif vs.translation_score >= 50:
        reasons.append("翻译适配度一般，可尝试")
    if vs.market_score >= 80:
        reasons.append("内容类型与中国市场高度匹配")
    if vs.cost_score >= 70:
        reasons.append("制作成本低，加工容易")
    if vs.quality_score >= 80:
        reasons.append("视频内容质量高")
    cat_names = {
        "tech": "科技", "education": "教育", "science": "科普",
        "gaming": "游戏", "fitness": "健身", "music": "音乐",
    }
    if vs.category and vs.category in cat_names:
        reasons.append(f"{cat_names[vs.category]}类内容在B站表现好")

    if not reasons:
        reasons.append("综合评分一般，可参考评分详情")
    return "；".join(reasons)


async def _seed_default_sources(db: AsyncSession) -> None:
    """Seed curated YouTube channel sources if none exist."""
    from app.models.discovery import DiscoverySource

    existing = (await db.execute(select(DiscoverySource))).scalars().all()
    if existing:
        return

    defaults = [
        ("channel", "https://www.youtube.com/@mkbhd", "MKBHD (科技)"),
        ("channel", "https://www.youtube.com/@veritasium", "Veritasium (科普)"),
        ("channel", "https://www.youtube.com/@LinusTechTips", "Linus Tech Tips"),
        ("channel", "https://www.youtube.com/@TED", "TED Talks"),
        ("keyword", "tech review 2026", "科技评测搜索"),
        ("keyword", "science explained", "科普解说搜索"),
        ("keyword", "learn English", "英语教学搜索"),
        ("keyword", "home workout routine", "健身训练搜索"),
    ]
    for stype, svalue, label in defaults:
        db.add(DiscoverySource(
            type=stype, source_value=svalue, label=label,
            enabled=True, scan_interval_hours=24, max_results_per_scan=10,
        ))
    await db.commit()
    logger.info("Seeded %d default discovery sources", len(defaults))


async def _curated_fallback(db: AsyncSession) -> list[dict]:
    """Fallback: score curated popular videos when trending scrape fails."""
    from app.services.scoring.metrics import fetch_batch_metrics

    # Curated list of popular recent tech/science/education videos
    curated_ids = [
        "dQw4w9WgXcQ",  # placeholder — replace with real trending IDs
    ]

    # Actually, use keyword search for a reliable fallback
    popular_searches = [
        "tech review 2026", "science documentary",
        "learn English conversation", "space exploration",
    ]

    all_videos = []
    for kw in popular_searches[:2]:  # Just 2 to keep things fast
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp", "--flat-playlist", "--dump-json",
            "--playlist-end", "8",
            f"ytsearch8:{kw}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            continue
        for line in stdout.decode("utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                all_videos.append({
                    "youtube_id": data.get("id") or "",
                    "title": data.get("title") or "",
                    "channel_name": data.get("uploader") or data.get("channel") or "",
                    "channel_id": data.get("channel_id") or "",
                    "duration_sec": float(data.get("duration") or 0),
                    "view_count": int(data.get("view_count") or 0),
                    "thumbnail_url": data.get("thumbnail") or "",
                })
            except json.JSONDecodeError:
                continue

    return all_videos


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
