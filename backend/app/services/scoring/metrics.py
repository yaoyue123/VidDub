"""YouTube video metrics fetching.

Data sources (tried in order):
1. YouTube Data API v3 (if API key configured)
2. yt-dlp --dump-json (public metadata, no API key needed)
"""

import asyncio
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def fetch_video_metrics(
    youtube_id: str,
    *,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """Fetch video metrics from best available source.

    Args:
        youtube_id: YouTube video ID (11 chars).
        api_key: Optional YouTube Data API v3 key.

    Returns:
        Dict with: view_count, like_count, comment_count, published_at,
        duration_sec, title, channel_name, channel_id, has_captions,
        tags, language, category_id, thumbnail_url, subscriber_count (approx).
    """
    # Try API first (fast, reliable, includes all stats)
    if api_key:
        try:
            return await _fetch_via_api(youtube_id, api_key)
        except Exception as e:
            logger.debug("YouTube API fetch failed, falling back: %s", e)

    # Fallback to yt-dlp (slower, fewer stats, but always works)
    return await _fetch_via_ytdlp(youtube_id)


async def fetch_batch_metrics(
    youtube_ids: list[str],
    *,
    api_key: Optional[str] = None,
    max_concurrent: int = 10,
) -> dict[str, dict[str, Any]]:
    """Fetch metrics for multiple videos concurrently.

    Returns:
        {youtube_id: metrics_dict}
    """
    sem = asyncio.Semaphore(max_concurrent)

    async def _one(yid: str) -> tuple[str, dict[str, Any]]:
        async with sem:
            try:
                return yid, await fetch_video_metrics(yid, api_key=api_key)
            except Exception as e:
                logger.warning("Failed to fetch metrics for %s: %s", yid, e)
                return yid, {"error": str(e)}

    tasks = [_one(yid) for yid in youtube_ids]
    results = dict(await asyncio.gather(*tasks))
    return results


async def _fetch_via_api(youtube_id: str, api_key: str) -> dict[str, Any]:
    """Fetch via YouTube Data API v3."""
    import httpx

    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "statistics,snippet,contentDetails",
        "id": youtube_id,
        "key": api_key,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    items = data.get("items", [])
    if not items:
        raise ValueError(f"YouTube video not found: {youtube_id}")

    item = items[0]
    stats = item.get("statistics", {})
    snippet = item.get("snippet", {})
    content = item.get("contentDetails", {})

    # Parse duration (ISO 8601 → seconds)
    duration_sec = _parse_iso8601_duration(content.get("duration", "PT0S"))

    return {
        "youtube_id": youtube_id,
        "view_count": int(stats.get("viewCount", 0)),
        "like_count": int(stats.get("likeCount", 0)),
        "comment_count": int(stats.get("commentCount", 0)),
        "published_at": snippet.get("publishedAt", ""),
        "duration_sec": duration_sec,
        "title": snippet.get("title", ""),
        "channel_name": snippet.get("channelTitle", ""),
        "channel_id": snippet.get("channelId", ""),
        "has_captions": snippet.get("defaultAudioLanguage") is not None,
        "tags": snippet.get("tags") or [],
        "language": snippet.get("defaultAudioLanguage") or "en",
        "category_id": snippet.get("categoryId", ""),
        "thumbnail_url": (
            snippet.get("thumbnails", {}).get("medium", {}).get("url", "")
        ),
        "subscriber_count": 0,  # Not available from videos.list
        "speaker_count": 1,     # Not available from API
        "source": "api",
    }


async def _fetch_via_ytdlp(youtube_id: str) -> dict[str, Any]:
    """Fetch via yt-dlp (no API key needed, but slower)."""
    url = f"https://www.youtube.com/watch?v={youtube_id}"

    proc = await asyncio.create_subprocess_exec(
        "yt-dlp", "--dump-json", "--no-playlist", "--skip-download",
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace")[-200:]
        raise RuntimeError(f"yt-dlp failed for {youtube_id}: {err}")

    raw = json.loads(stdout.decode("utf-8"))

    duration_sec = float(raw.get("duration") or 0)
    captions = raw.get("subtitles") or raw.get("automatic_captions")

    return {
        "youtube_id": youtube_id,
        "view_count": int(raw.get("view_count") or 0),
        "like_count": int(raw.get("like_count") or 0),
        "comment_count": int(raw.get("comment_count") or 0),
        "published_at": raw.get("upload_date") or "",
        "duration_sec": duration_sec,
        "title": raw.get("title") or raw.get("fulltitle") or "",
        "channel_name": raw.get("uploader") or raw.get("channel") or "",
        "channel_id": raw.get("channel_id") or raw.get("uploader_id") or "",
        "has_captions": "manual" if captions else False,
        "tags": raw.get("tags") or [],
        "language": raw.get("language") or "en",
        "category_id": "",
        "thumbnail_url": raw.get("thumbnail") or "",
        "subscriber_count": int(
            raw.get("channel_follower_count") or 0
        ),
        "speaker_count": 1,
        "source": "yt-dlp",
    }


def _parse_iso8601_duration(duration: str) -> float:
    """Parse ISO 8601 duration (e.g., PT1H2M3S) to seconds."""
    import re

    match = re.match(
        r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$",
        duration,
    )
    if not match:
        return 0.0

    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = float(match.group(4) or 0)

    return days * 86400 + hours * 3600 + minutes * 60 + seconds
