"""
yt-dlp Python API 封装

Provides search, channel scanning, metadata extraction, and video download.
All download operations are synchronous (yt-dlp is blocking) and should be
run via asyncio.to_thread / loop.run_in_executor.

All yt-dlp extraction calls go through the global YtDlpWrapper singleton
for shared rate limiting, circuit breaking, cookie management, and
extractor-args configuration.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.services.ytdlp_wrapper import YtDlpWrapper, get_ytdlp_wrapper

logger = logging.getLogger(__name__)


@dataclass
class VideoMeta:
    """Normalized video metadata from yt-dlp extraction."""
    youtube_id: str
    title: str
    channel: str
    channel_url: str = ""
    duration: Optional[int] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    thumbnail_url: Optional[str] = None
    description: Optional[str] = ""
    tags: list[str] = field(default_factory=list)
    webpage_url: str = ""


class YoutubeService:
    """yt-dlp Python API wrapper for video discovery and download.

    All yt-dlp extraction operations delegate to the shared
    :class:`YtDlpWrapper` singleton for rate limiting, circuit breaking,
    cookie management, and extractor-args configuration.
    """

    DOWNLOAD_OPTS_TEMPLATE: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ignoreerrors": True,
        "no_color": True,
        "sleep_interval": 1,
        "max_sleep_interval": 3,
        "merge_output_format": "mp4",
        "outtmpl": "",  # set per-call
        "progress_hooks": [],  # set per-call
        "postprocessors": [],
        # Reliability
        "retries": 10,
        "fragment_retries": 10,
        "continuedl": True,
        "throttledratelimit": 100_000,
    }

    def __init__(
        self,
        download_dir: str = "./downloads",
        max_resolution: int = 1080,
        ytdlp_wrapper: Optional[YtDlpWrapper] = None,
    ):
        self.download_dir = download_dir
        self.max_resolution = max_resolution
        self._wrapper = ytdlp_wrapper or get_ytdlp_wrapper()
        os.makedirs(self.download_dir, exist_ok=True)

    # ── Search ──

    def search_sync(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        """Search YouTube (synchronous, run via executor)."""
        try:
            entries = self._wrapper.search_sync(query, max_results=max_results)
        except Exception as e:
            logger.error("yt-dlp search failed: %s", e)
            return []

        return [self._normalize_entry(e) for e in entries if e]

    async def search(
        self, query: str, max_results: int = 20
    ) -> list[dict[str, Any]]:
        """Search YouTube (async)."""
        try:
            entries = await self._wrapper.search(query, max_results=max_results)
        except Exception as e:
            logger.error("yt-dlp search failed: %s", e)
            return []

        return [self._normalize_entry(e) for e in entries if e]

    # ── Channel scan ──

    def get_channel_videos_sync(self, channel_url: str, max_results: int = 50) -> list[dict[str, Any]]:
        """Scan channel for videos (synchronous)."""
        try:
            entries = self._wrapper.get_channel_videos_sync(channel_url, max_results=max_results)
        except Exception as e:
            logger.error("yt-dlp channel scan failed: %s", e)
            return []

        return [self._normalize_entry(e) for e in entries if e][:max_results]

    async def get_channel_videos(
        self, channel_url: str, max_results: int = 50
    ) -> list[dict[str, Any]]:
        """Scan channel for videos (async)."""
        try:
            entries = await self._wrapper.get_channel_videos(channel_url, max_results=max_results)
        except Exception as e:
            logger.error("yt-dlp channel scan failed: %s", e)
            return []

        return [self._normalize_entry(e) for e in entries if e][:max_results]

    # ── Single video info (full metadata) ──

    def get_video_info_sync(self, url: str) -> Optional[dict[str, Any]]:
        """Get full metadata for a single video (synchronous)."""
        info = self._wrapper.get_video_info_sync(url)
        if info is None:
            return None
        return self._normalize_entry(info)

    async def get_video_info(self, url: str) -> Optional[dict[str, Any]]:
        """Get full metadata for a single video (async)."""
        info = await self._wrapper.get_video_info(url)
        if info is None:
            return None
        return self._normalize_entry(info)

    # ── Download ──

    def _build_format(self) -> str:
        """Build yt-dlp format string with resolution cap.

        Structure: bestvideo capped + bestaudio (merged via ffmpeg),
        fallback to best muxed stream for older videos that lack
        separate audio/video streams.
        """
        return (
            f"bestvideo[height<={self.max_resolution}]+bestaudio/"
            f"best[height<={self.max_resolution}]/"
            f"best"
        )

    def download_sync(
        self,
        url: str,
        progress_hook: Optional[Callable] = None,
        cookies_file: Optional[str] = None,
    ) -> Optional[str]:
        """Download a video (synchronous, run via executor).

        Returns the output file path, or None on failure.
        """
        from yt_dlp import YoutubeDL

        hooks: list[Callable] = []
        if progress_hook:
            hooks.append(progress_hook)

        opts: dict[str, Any] = {
            **self.DOWNLOAD_OPTS_TEMPLATE,
            "format": self._build_format(),
            "outtmpl": os.path.join(self.download_dir, "%(id)s.%(ext)s"),
            "progress_hooks": hooks,
        }
        if cookies_file and os.path.exists(cookies_file):
            opts["cookiefile"] = cookies_file

        with YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    return None
                # Determine actual file path
                ext = info.get("ext", "mp4")
                youtube_id = info.get("id", "unknown")
                filepath = os.path.join(self.download_dir, f"{youtube_id}.{ext}")
                if os.path.exists(filepath):
                    return filepath
                # yt-dlp might have merged; check common patterns
                for candidate in (
                    os.path.join(self.download_dir, f"{youtube_id}.mp4"),
                    os.path.join(self.download_dir, f"{youtube_id}.mkv"),
                    os.path.join(self.download_dir, f"{youtube_id}.webm"),
                ):
                    if os.path.exists(candidate):
                        return candidate
                return filepath  # best guess
            except Exception as e:
                logger.error("yt-dlp download failed for %s: %s", url, e)
                return None

    async def download(
        self,
        url: str,
        progress_hook: Optional[Callable] = None,
        cookies_file: Optional[str] = None,
    ) -> Optional[str]:
        """Download a video (async)."""
        import asyncio
        return await asyncio.to_thread(
            self.download_sync, url, progress_hook, cookies_file
        )

    # ── Subtitle extraction (prep for Phase 3) ──

    def get_subtitles_sync(self, url: str, lang: str = "en") -> Optional[list[dict[str, Any]]]:
        """Extract available subtitles for a video."""
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": [lang],
            "skip_download": True,
            "ignoreerrors": True,
        }
        try:
            info = self._wrapper.extract_info_sync(opts, url)
            if info is None:
                return None
            return info.get("subtitles", {}).get(lang)
        except Exception as e:
            logger.error("Failed to get subtitles: %s", e)
            return None

    # ── Internal helpers ──

    def _normalize_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Normalize a yt-dlp entry to a consistent structure."""
        return {
            "youtube_id": entry.get("id", ""),
            "title": entry.get("title", ""),
            "channel": entry.get("channel", entry.get("uploader", "")),
            "channel_url": entry.get("channel_url", ""),
            "duration": entry.get("duration"),
            "view_count": entry.get("view_count"),
            "like_count": entry.get("like_count"),
            "comment_count": entry.get("comment_count"),
            "thumbnail_url": entry.get("thumbnail", entry.get("thumbnails", [{}])[0].get("url") if entry.get("thumbnails") else None),
            "description": entry.get("description", ""),
            "tags": entry.get("tags", []),
            "webpage_url": entry.get("webpage_url", ""),
        }
