"""Discovery pipeline — orchestrate discovery sources, score, deduplicate."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update

from app.core.database import async_session_factory
from app.models.discovery import DiscoverySource, DiscoveryResult
from app.models.video import Video
from app.models.video_score import VideoScore
from app.services.scoring.metrics import fetch_video_metrics
from app.services.scoring.scorer import score_video

logger = logging.getLogger(__name__)


async def run_discovery(source_id: int) -> list[DiscoveryResult]:
    """Run discovery for a single source: fetch → score → deduplicate → store.

    Returns newly created DiscoveryResult rows.
    """
    async with async_session_factory() as session:
        source = (
            await session.execute(
                select(DiscoverySource).where(DiscoverySource.id == source_id),
            )
        ).scalar_one_or_none()

        if not source or not source.enabled:
            return []

    # 1. Fetch videos from the source
    video_ids = await _fetch_from_source(source)

    if not video_ids:
        logger.info("Discovery source %d returned no videos", source_id)
        return []

    # 2. Deduplicate against existing videos and discovery results
    new_ids = await _deduplicate(video_ids)

    if not new_ids:
        logger.info("Discovery source %d: all %d videos already known",
                     source_id, len(video_ids))
        return []

    # 3. Score each new video
    metrics_map = await fetch_video_metrics(new_ids)
    results = []

    async with async_session_factory() as session:
        for yid in new_ids:
            metrics = metrics_map.get(yid, {})
            if "error" in metrics:
                continue

            # Quick category classification
            from app.services.scoring.classifier import classify_video_content
            try:
                from app.services.siliconflow.client import get_async_client
                async with get_async_client(timeout=30.0) as client:
                    category = await classify_video_content(
                        metrics.get("title", ""),
                        tags=metrics.get("tags", []),
                        channel_id=metrics.get("channel_id", ""),
                        client=client,
                    )
            except Exception:
                category = "other"

            scored = score_video(metrics, category=category)

            # Store as VideoScore if not exists
            existing_score = (
                await session.execute(
                    select(VideoScore).where(VideoScore.youtube_id == yid),
                )
            ).scalar_one_or_none()

            if not existing_score:
                session.add(VideoScore(
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
                    category=category,
                ))

            # Store discovery result
            result = DiscoveryResult(
                source_id=source.id,
                youtube_id=yid,
                title=metrics.get("title", ""),
                channel_name=metrics.get("channel_name", ""),
                composite_score=scored["composite_score"],
                status="scored",
                discovered_at=datetime.now(timezone.utc),
            )
            session.add(result)
            results.append(result)

        # Update last_scanned_at
        await session.execute(
            update(DiscoverySource)
            .where(DiscoverySource.id == source_id)
            .values(last_scanned_at=datetime.now(timezone.utc)),
        )
        await session.commit()

    logger.info(
        "Discovery source %d: found %d, new %d, scored %d",
        source_id, len(video_ids), len(new_ids), len(results),
    )
    return results


async def run_all_sources() -> dict[int, list[DiscoveryResult]]:
    """Run discovery for all enabled sources. Returns {source_id: results}."""
    async with async_session_factory() as session:
        sources = (
            await session.execute(
                select(DiscoverySource).where(DiscoverySource.enabled == True),
            )
        ).scalars().all()

    all_results = {}
    for source in sources:
        try:
            results = await run_discovery(source.id)
            all_results[source.id] = results
        except Exception as e:
            logger.error("Discovery source %d failed: %s", source.id, e)
            all_results[source.id] = []

    return all_results


async def _fetch_from_source(
    source: DiscoverySource,
) -> list[str]:
    """Fetch video IDs from a discovery source."""
    if source.type == "channel":
        return await _fetch_channel(source.source_value, source.max_results_per_scan)
    elif source.type == "keyword":
        return await _fetch_keyword(source.source_value, source.max_results_per_scan)
    elif source.type == "trending":
        return await _fetch_trending_ids(source.max_results_per_scan)
    else:
        logger.warning("Unknown discovery source type: %s", source.type)
        return []


async def _fetch_channel(url: str, max_results: int) -> list[str]:
    """Get recent video IDs from a channel via yt-dlp."""
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp", "--flat-playlist", "--dump-json",
        "--playlist-end", str(max_results),
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return []

    ids = []
    for line in stdout.decode("utf-8").strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            yid = data.get("id") or ""
            if yid:
                ids.append(yid)
        except json.JSONDecodeError:
            continue
    return ids


async def _fetch_keyword(keyword: str, max_results: int) -> list[str]:
    """Search YouTube for keyword, return video IDs."""
    search = f"ytsearch{max_results}:{keyword}"
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp", "--flat-playlist", "--dump-json",
        "--playlist-end", str(max_results),
        search,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return []

    ids = []
    for line in stdout.decode("utf-8").strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            yid = data.get("id") or ""
            if yid:
                ids.append(yid)
        except json.JSONDecodeError:
            continue
    return ids


async def _fetch_trending_ids(max_results: int) -> list[str]:
    """Get trending video IDs from YouTube."""
    from app.services.scoring.discovery import scrape_trending
    results = await scrape_trending(max_per_category=max_results // 4 or 5)
    return [r["youtube_id"] for r in results if r.get("youtube_id")]


async def _deduplicate(video_ids: list[str]) -> list[str]:
    """Filter out already-known video IDs.

    Checks against:
    - videos table (already processed/downloaded)
    - discovery_results table (already discovered)
    - video_scores table (already scored)
    """
    if not video_ids:
        return []

    async with async_session_factory() as session:
        # Check videos table
        existing_videos = (
            await session.execute(
                select(Video.youtube_id).where(
                    Video.youtube_id.in_(video_ids),
                ),
            )
        ).scalars().all()
        existing_set = set(existing_videos)

        # Check discovery_results
        existing_discoveries = (
            await session.execute(
                select(DiscoveryResult.youtube_id).where(
                    DiscoveryResult.youtube_id.in_(video_ids),
                ),
            )
        ).scalars().all()
        existing_set.update(existing_discoveries)

        # Check video_scores
        existing_scores = (
            await session.execute(
                select(VideoScore.youtube_id).where(
                    VideoScore.youtube_id.in_(video_ids),
                ),
            )
        ).scalars().all()
        existing_set.update(existing_scores)

    return [yid for yid in video_ids if yid not in existing_set]
