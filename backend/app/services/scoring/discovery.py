"""Discovery engine — channel recommender, trending scraper, keyword miner."""

import asyncio
import json
import logging
import subprocess as _subprocess
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, update

from app.core.database import async_session_factory
from app.models.discovery import DiscoverySource, DiscoveryResult
from app.models.video_score import VideoScore

logger = logging.getLogger(__name__)


async def _run_ytdlp(cmd: list[str]) -> tuple[int, bytes, bytes]:
    """Run yt-dlp subprocess. Cross-platform: uses asyncio subprocess on
    Linux/macOS, falls back to subprocess.run + thread pool on Windows
    where the event loop doesn't support subprocess."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return (proc.returncode, stdout, stderr)
    except NotImplementedError:
        def _run():
            return _subprocess.run(cmd, capture_output=True, timeout=120)
        result = await asyncio.to_thread(_run)
        return (result.returncode, result.stdout, result.stderr)


async def _ytdlp_json(cmd: list[str]) -> list[dict]:
    """Run yt-dlp --dump-json and parse each line as JSON."""
    code, stdout, stderr = await _run_ytdlp(cmd)
    if code != 0:
        logger.debug("yt-dlp failed: %s", stderr.decode("utf-8", errors="replace")[-200:])
        return []
    results = []
    for line in stdout.decode("utf-8").strip().split("\n"):
        if not line.strip():
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return results

# Trending YouTube categories (browse IDs)
TRENDING_CATEGORIES = {
    "tech": "https://www.youtube.com/feed/trending?bp=4gIuGgsQyYhcYSixwdcE",
    "science": "https://www.youtube.com/feed/trending?bp=4gIcGgsQ85pYYSixwdcE",
    "gaming": "https://www.youtube.com/feed/trending?bp=4gIcGhpnYW1pbmdfY29ycHVzX21vc3RfcG9wdWxhcg%3D%3D",
    "music": "https://www.youtube.com/feed/trending?bp=4gIcGghuYXdsdWNrAQsI1JpYYSixwdk%3D",
}


async def recommend_channels(
    seed_channel_id: Optional[str] = None,
    seed_category: Optional[str] = None,
    *,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Recommend similar channels based on seed.

    Uses YouTube search to find channels in the same category.
    Falls back to trending channels if no seed provided.
    """
    query = seed_category or "tech reviews"
    if seed_channel_id:
        query = f"channel similar to {seed_channel_id}"

    search_url = f"ytsearch{max_results}:{query} channel"

    items = await _ytdlp_json([
        "yt-dlp", "--flat-playlist", "--dump-json",
        "--playlist-end", str(max_results), search_url,
    ])

    channels = []
    for data in items:
        channels.append({
            "channel_id": data.get("channel_id") or data.get("uploader_id", ""),
            "channel_name": data.get("uploader") or data.get("channel", ""),
            "channel_url": data.get("channel_url") or data.get("uploader_url", ""),
            "subscriber_count": int(data.get("channel_follower_count") or 0),
            "video_count": int(data.get("playlist_count") or 0),
            "description": (data.get("description") or "")[:200],
        })

    return channels


async def scrape_trending(
    categories: Optional[list[str]] = None,
    *,
    max_per_category: int = 10,
) -> list[dict[str, Any]]:
    """Scrape trending videos from YouTube categories.

    Returns list of video metadata dicts with youtube_id, title, etc.
    """
    cats = categories or list(TRENDING_CATEGORIES.keys())
    results = []

    sem = asyncio.Semaphore(4)

    async def _scrape_one(cat: str):
        async with sem:
            url = TRENDING_CATEGORIES.get(cat)
            if not url:
                return

            items = await _ytdlp_json([
                "yt-dlp", "--flat-playlist", "--dump-json",
                "--playlist-end", str(max_per_category), url,
            ])
            for data in items:
                results.append({
                    "youtube_id": data.get("id") or "",
                    "title": data.get("title") or "",
                    "channel_name": data.get("uploader") or data.get("channel") or "",
                    "channel_id": data.get("channel_id") or "",
                    "duration_sec": float(data.get("duration") or 0),
                    "view_count": int(data.get("view_count") or 0),
                    "category": cat,
                })

    await asyncio.gather(*[_scrape_one(c) for c in cats])
    return results


def mine_keywords(
    successful_categories: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Mine search keywords using LLM + category heuristics.

    Returns list of {keyword, rationale, expected_quality} dicts.
    """
    # Curated keyword templates per high-performing category
    templates: dict[str, list[dict[str, Any]]] = {
        "tech": [
            {"keyword": "tech review 2026", "rationale": "科技评测类在B站流量稳定"},
            {"keyword": "new gadget unboxing", "rationale": "开箱类视频互动率高"},
            {"keyword": "PC build guide", "rationale": "装机教程长期热度高"},
            {"keyword": "smartphone comparison", "rationale": "手机横评对比受欢迎"},
        ],
        "education": [
            {"keyword": "explained simply", "rationale": "科普类在B站知识区流量好"},
            {"keyword": "how it works animation", "rationale": "可视化科普适合搬运"},
            {"keyword": "learn English conversation", "rationale": "英语教学类需求巨大"},
            {"keyword": "history documentary", "rationale": "历史纪录片有稳定观众"},
        ],
        "science": [
            {"keyword": "science experiment", "rationale": "实验类视觉性强，语言需求低"},
            {"keyword": "space exploration 2026", "rationale": "太空探索类高关注"},
            {"keyword": "physics visualized", "rationale": "物理可视化适合无对白搬运"},
        ],
        "fitness": [
            {"keyword": "home workout no equipment", "rationale": "居家健身无需语言"},
            {"keyword": "stretching routine", "rationale": "拉伸类内容语言需求极低"},
        ],
        "gaming": [
            {"keyword": "game review 2026", "rationale": "游戏评测在B站核心受众"},
            {"keyword": "esports highlights", "rationale": "电竞高光时刻无需翻译"},
        ],
    }

    keywords = []
    cats = successful_categories or ["tech", "education", "science"]
    if not cats:
        cats = ["tech", "education", "science"]

    for cat in cats:
        if cat in templates:
            keywords.extend(templates[cat])

    # Fallback: if no keywords found, use defaults
    if not keywords:
        for cat in ["tech", "education", "science"]:
            keywords.extend(templates.get(cat, []))

    # Deduplicate by keyword
    seen = set()
    unique = []
    for kw in keywords:
        if kw["keyword"] not in seen:
            seen.add(kw["keyword"])
            unique.append(kw)

    return unique[:20]
