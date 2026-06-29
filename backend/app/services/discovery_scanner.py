"""Phase 8: DiscoveryScanner -- Single-coordinator APScheduler scanner for all DiscoverySource types.

Design (per D-v5.1-01, D-v5.1-02):
- Single APScheduler coordinator job (not per-source jobs)
- Coordinator ticks on short interval and scans sources that are due
- Type dispatch: keyword -> yt-dlp search, creator -> yt-dlp channel scan
- Per-source filters applied before dedup
- Dedup against Video.youtube_id + DiscoveryResult.youtube_id
- Stores new results as DiscoveryResult rows
- Writes DiscoveryScanLog per scan
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.database import async_session_factory
from app.models.discovery import DiscoverySource, DiscoveryResult
from app.models.discovery_scan_log import DiscoveryScanLog
from app.models.video import Video
from app.services.ytdlp_wrapper import get_ytdlp_wrapper

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Scan result for a single DiscoverySource scan."""
    source_id: int
    found_count: int
    added_count: int
    status: str = "success"  # success | partial | failed
    error_msg: Optional[str] = None


class DiscoveryScanner:
    """Single-coordinator APScheduler scanner for DiscoverySource items.

    Unlike ChannelScanner (one job per channel),
    DiscoveryScanner uses a single coordinator loop that ticks on a
    configurable interval and scans all due sources. This prevents
    thundering herd when many sources are configured (D-v5.1-01).
    """

    COORDINATOR_JOB_ID = "discovery_scanner_coordinator"
    DEFAULT_TICK_MINUTES = 15

    def __init__(
        self,
        max_concurrent: int = 3,
        tick_minutes: int = DEFAULT_TICK_MINUTES,
    ):
        self._max_concurrent = max_concurrent
        self._tick_minutes = tick_minutes
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._semaphore = asyncio.Semaphore(max_concurrent)

    # ── Lifecycle ──

    async def start(self) -> None:
        """Start the coordinator scheduler."""
        if self._scheduler is not None:
            logger.warning("DiscoveryScanner already started")
            return

        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._coordinator_tick,
            trigger=IntervalTrigger(minutes=self._tick_minutes),
            id=self.COORDINATOR_JOB_ID,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=None,
        )
        self._scheduler.start()

        logger.info(
            "DiscoveryScanner started: coordinator tick every %d minutes (max_concurrent=%d)",
            self._tick_minutes, self._max_concurrent,
        )

    async def stop(self) -> None:
        """Stop the scheduler."""
        if self._scheduler is None:
            return
        self._scheduler.shutdown(wait=False)
        self._scheduler = None
        logger.info("DiscoveryScanner stopped")

    # ── Coordinator tick ──

    async def _coordinator_tick(self) -> None:
        """APScheduler-coordinated tick: load due sources and scan them."""
        try:
            due_sources = await self._get_due_sources()
            if not due_sources:
                logger.debug("Coordinator tick: no sources due for scanning")
                return

            logger.info(
                "Coordinator tick: %d source(s) due for scanning",
                len(due_sources),
            )

            async def scan_wrapper(source_id: int) -> None:
                async with self._semaphore:
                    try:
                        await self._scan_once_impl(source_id)
                    except Exception as e:
                        logger.error(
                            "Coordinator: source %d scan failed: %s",
                            source_id, e, exc_info=True,
                        )

            await asyncio.gather(*[scan_wrapper(s.id) for s in due_sources])

            logger.info(
                "Coordinator tick: scanned %d source(s)",
                len(due_sources),
            )
        except Exception as e:
            logger.error("Coordinator tick error: %s", e, exc_info=True)

    async def _get_due_sources(self) -> list[DiscoverySource]:
        """Query enabled DiscoverySource items that are due for scanning.

        Returns sources where last_scanned_at is None (never scanned)
        OR last_scanned_at + scan_interval_hours is past the threshold.
        """
        async with async_session_factory() as session:
            # Sources that have never been scanned
            result = await session.execute(
                select(DiscoverySource).where(
                    DiscoverySource.enabled.is_(True),
                    DiscoverySource.last_scanned_at.is_(None),
                )
            )
            never_scanned = list(result.scalars().all())

            # Sources past their scan interval
            threshold = datetime.now(timezone.utc) - timedelta(hours=9999)
            result = await session.execute(
                select(DiscoverySource).where(
                    DiscoverySource.enabled.is_(True),
                    DiscoverySource.last_scanned_at.isnot(None),
                    DiscoverySource.last_scanned_at < threshold,
                )
            )
            due = list(result.scalars().all())

        return never_scanned + due

    # ── Public scan entry point ──

    async def scan_once(self, source_id: int) -> ScanResult:
        """Scan a single discovery source (public entry point).

        Uses semaphore to respect max_concurrent limit.
        Returns ScanResult with found/add counts and status.
        """
        async with self._semaphore:
            return await self._scan_once_impl(source_id)

    async def _scan_once_impl(self, source_id: int) -> ScanResult:
        """Execute a single scan: fetch -> filter -> dedup -> store -> log.

        Steps:
        1. Load DiscoverySource by id
        2. Fetch via yt-dlp (type dispatch: keyword/creator)
        3. Apply per-source filters
        4. Deduplicate against Video + DiscoveryResult tables
        5. Store new results as DiscoveryResult rows
        6. Update last_scanned_at
        7. Write DiscoveryScanLog
        """
        # 1. Load source
        async with async_session_factory() as session:
            result = await session.execute(
                select(DiscoverySource).where(DiscoverySource.id == source_id)
            )
            source = result.scalar_one_or_none()

        if source is None:
            return ScanResult(
                source_id=source_id, found_count=0, added_count=0,
                status="failed", error_msg="Source not found",
            )
        if not source.enabled:
            return ScanResult(
                source_id=source_id, found_count=0, added_count=0,
                status="failed", error_msg="Source is disabled",
            )

        # 2. Fetch via yt-dlp (type dispatch)
        yt = get_ytdlp_wrapper()
        try:
            if source.type == "keyword":
                fetched = await yt.search(
                    source.source_value,
                    max_results=source.max_results_per_scan or 20,
                )
            elif source.type == "creator":
                fetched = await yt.get_channel_videos(
                    source.source_value,
                    max_results=source.max_results_per_scan or 20,
                )
            else:
                return ScanResult(
                    source_id=source_id, found_count=0, added_count=0,
                    status="failed",
                    error_msg=f"Unsupported source type: {source.type}",
                )
        except Exception as e:
            logger.error(
                "Discovery source %d (type=%s) fetch failed: %s",
                source_id, source.type, e,
            )
            error_msg = str(e)
            await self._write_scan_log(
                source_id, 0, 0, "failed", error_msg,
            )
            return ScanResult(
                source_id=source_id, found_count=0, added_count=0,
                status="failed", error_msg=error_msg,
            )

        found_count = len(fetched)

        # 3. Apply filters
        filtered = self._apply_filters(fetched, source)

        # 4. Deduplicate
        deduped = await self._deduplicate(filtered)

        # 5. Store results
        added_count = await self._store_results(deduped, source_id)

        # 6. Update last_scanned_at
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            await session.execute(
                update(DiscoverySource)
                .where(DiscoverySource.id == source_id)
                .values(last_scanned_at=now)
            )
            await session.commit()

        # 7. Determine status and write scan log
        if added_count == 0 and found_count > 0:
            status = "partial" if filtered else "success"
        elif added_count < found_count:
            status = "partial"
        else:
            status = "success"

        await self._write_scan_log(source_id, found_count, added_count, status, None)

        logger.info(
            "Discovery source %d (%s) scanned: found=%d, after_filter=%d, added=%d, status=%s",
            source_id, source.type, found_count, len(deduped), added_count, status,
        )
        return ScanResult(
            source_id=source_id,
            found_count=found_count,
            added_count=added_count,
            status=status,
            error_msg=None,
        )

    # ── Filters ──

    def _apply_filters(
        self,
        videos: list[dict],
        source: DiscoverySource,
    ) -> list[dict]:
        """Apply per-source filter columns to fetched videos.

        Filters: min_views, max_views, min_duration_sec, max_duration_sec,
        published_within_hours. If a filter column is None, the filter is
        not applied. Videos missing filter-relevant fields are excluded unless
        the missing field would mean the filter is inactive.
        """
        out: list[dict] = []
        for v in videos:
            views = v.get("view_count")
            duration = v.get("duration")
            upload_date = v.get("upload_date")  # yt-dlp format: YYYYMMDD

            if source.filter_min_views is not None:
                if views is None or views < source.filter_min_views:
                    continue
            if source.filter_max_views is not None:
                if views is not None and views > source.filter_max_views:
                    continue
            if source.filter_min_duration_sec is not None:
                if duration is None or duration < source.filter_min_duration_sec:
                    continue
            if source.filter_max_duration_sec is not None:
                if duration is not None and duration > source.filter_max_duration_sec:
                    continue
            if source.filter_published_within_hours is not None:
                if not upload_date:
                    # No date info -- include by default
                    pass
                else:
                    try:
                        pub = datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)
                        if (datetime.now(timezone.utc) - pub) > timedelta(
                            hours=source.filter_published_within_hours,
                        ):
                            continue
                    except (ValueError, TypeError):
                        pass
            out.append(v)
        return out

    # ── Deduplication ──

    async def _deduplicate(self, videos: list[dict]) -> list[dict]:
        """Remove videos already in Video or DiscoveryResult tables.

        Checks both Video.youtube_id (downloaded/tracking) and
        DiscoveryResult.youtube_id (previously discovered).
        """
        if not videos:
            return []

        youtube_ids = [v.get("youtube_id") for v in videos if v.get("youtube_id")]
        if not youtube_ids:
            return []

        async with async_session_factory() as session:
            # Check Video table
            video_result = await session.execute(
                select(Video.youtube_id).where(Video.youtube_id.in_(youtube_ids))
            )
            existing_video_ids = {row[0] for row in video_result.all()}

            # Check DiscoveryResult table
            dr_result = await session.execute(
                select(DiscoveryResult.youtube_id).where(
                    DiscoveryResult.youtube_id.in_(youtube_ids)
                )
            )
            existing_dr_ids = {row[0] for row in dr_result.all()}

        existing_ids = existing_video_ids | existing_dr_ids
        deduped = [v for v in videos if v.get("youtube_id") not in existing_ids]

        if existing_ids:
            logger.info(
                "Dedup: %d videos filtered (%d existing in Video, %d in DiscoveryResult)",
                len(videos) - len(deduped),
                len(existing_video_ids),
                len(existing_dr_ids),
            )

        return deduped

    # ── Store results ──

    async def _store_results(self, videos: list[dict], source_id: int) -> int:
        """Insert deduped videos as DiscoveryResult rows.

        Handles IntegrityError per-entry (race condition on youtube_id).
        Returns count of successfully added rows.
        """
        if not videos:
            return 0

        added = 0
        async with async_session_factory() as session:
            for v in videos:
                yt_id = v.get("youtube_id")
                if not yt_id:
                    continue

                result = DiscoveryResult(
                    source_id=source_id,
                    youtube_id=yt_id,
                    title=v.get("title", ""),
                    channel_name=v.get("channel", ""),
                    duration_sec=v.get("duration"),
                    view_count=v.get("view_count"),
                    like_count=v.get("like_count"),
                    thumbnail_url=v.get("thumbnail_url"),
                    published_at=v.get("upload_date") or v.get("published_at"),
                    discovered_at=datetime.now(timezone.utc),
                    status="new",
                )
                session.add(result)
                try:
                    await session.flush()
                except IntegrityError:
                    await session.rollback()
                    continue
                added += 1

            await session.commit()

        return added

    # ── Scan log writing ──

    async def _write_scan_log(
        self,
        source_id: int,
        found_count: int,
        added_count: int,
        status: str,
        error_msg: Optional[str],
    ) -> None:
        """Write a DiscoveryScanLog entry for a completed scan.

        Errors during log writing are logged but not re-raised so that
        scan failures do not cascade from a failed log write.
        """
        try:
            async with async_session_factory() as session:
                session.add(DiscoveryScanLog(
                    source_id=source_id,
                    found_count=found_count,
                    added_count=added_count,
                    status=status,
                    error_msg=error_msg,
                ))
                await session.commit()
        except Exception as e:
            logger.error("Failed to write DiscoveryScanLog: %s", e)


# ── Global singleton accessor ──

_scanner: Optional[DiscoveryScanner] = None


def get_discovery_scanner() -> DiscoveryScanner:
    """Return the global DiscoveryScanner singleton.

    Creates a default instance on first call if not already set.
    """
    global _scanner
    if _scanner is None:
        _scanner = DiscoveryScanner()
    return _scanner


def set_discovery_scanner(scanner: Optional[DiscoveryScanner]) -> None:
    """Set the global DiscoveryScanner singleton.

    Used during application startup and in tests for injection.
    Pass None to reset.
    """
    global _scanner
    _scanner = scanner
