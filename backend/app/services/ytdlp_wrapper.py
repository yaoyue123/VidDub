"""
Centralized yt-dlp wrapper with sliding-window rate limiter, circuit breaker,
cookie file management, and extractor-args configuration.

All yt-dlp calls across the application go through YtDlpWrapper to ensure:
- Shared rate limiting prevents 429/403 throttling (Pitfall #1)
- Circuit breaker pauses all calls after N consecutive failures
- Cookie file path is read from config and passed to all operations
- Extractor-args are hot-reloadable via Config table (Pitfall #3)
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is open and calls are blocked."""
    pass


class YtDlpRateLimiter:
    """Sliding-window rate limiter for yt-dlp extraction calls.

    Enforces both max concurrency (via asyncio.Semaphore) and a minimum
    inter-request interval (via asyncio.Lock). Use as an async context manager::

        async with limiter:
            result = await extract_info(...)
    """

    def __init__(self, min_interval: float = 10.0, max_concurrent: int = 2) -> None:
        """Initialize the rate limiter.

        Args:
            min_interval: Minimum seconds between consecutive releases.
            max_concurrent: Maximum number of concurrent extractions.
        """
        self._min_interval = min_interval
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a rate-limited slot.

        Blocks until both a semaphore slot is available AND at least
        ``min_interval`` seconds have elapsed since the last release.
        """
        await self._semaphore.acquire()
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                wait = self._min_interval - elapsed
                logger.debug("Rate limiter: waiting %.2fs (min_interval=%.1f)", wait, self._min_interval)
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

    async def release(self) -> None:
        """Release the acquired slot."""
        self._semaphore.release()

    async def __aenter__(self) -> "YtDlpRateLimiter":
        await self.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> None:
        self.release()


class CircuitBreaker:
    """Circuit breaker for yt-dlp calls.

    Trips to OPEN state after ``failure_threshold`` consecutive failures,
    then stays open for ``recovery_timeout`` seconds before allowing a
    single trial (HALF-OPEN state).

    State transitions::

        closed --(N failures)--> open --(timeout elapsed)--> half-open
        half-open --(success)--> closed
        half-open --(failure)--> open (reset timer)
    """

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 300.0) -> None:
        """Initialize the circuit breaker.

        Args:
            failure_threshold: Number of consecutive failures before tripping open.
            recovery_timeout: Seconds to stay open before allowing a half-open trial.
        """
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._state: str = "closed"  # "closed" | "open" | "half-open"
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> str:
        """Return the current circuit breaker state: closed, open, or half-open."""
        return self._state

    @property
    def is_open(self) -> bool:
        """Return True if the circuit breaker is currently in the OPEN state."""
        return self._state == "open"

    async def call(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Execute *fn* through the circuit breaker (async entry point).

        If *fn* is a coroutine function it is awaited directly; otherwise it
        is dispatched via ``asyncio.to_thread`` so blocking calls (e.g.
        yt-dlp's synchronous API) do not block the event loop.

        Args:
            fn: The callable to execute (sync or async).
            *args: Positional arguments forwarded to *fn*.
            **kwargs: Keyword arguments forwarded to *fn*.

        Returns:
            The return value of *fn*.

        Raises:
            CircuitBreakerOpenError: If the circuit is open and the recovery
                timeout has not elapsed.
        """
        # State check
        if self._state == "open":
            if time.monotonic() - self._last_failure_time < self._recovery_timeout:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker is open (failure_count={self._failure_count}, "
                    f"recovery_remaining={self._recovery_timeout - (time.monotonic() - self._last_failure_time):.1f}s)"
                )
            logger.info("Circuit breaker: transitioning open -> half-open (trial)")
            self._state = "half-open"

        try:
            if asyncio.iscoroutinefunction(fn):
                result = await fn(*args, **kwargs)
            else:
                result = await asyncio.to_thread(fn, *args, **kwargs)
        except CircuitBreakerOpenError:
            raise
        except Exception as exc:
            self._failure_count += 1
            logger.warning(
                "Circuit breaker: call failed (%d/%d): %s: %s",
                self._failure_count, self._failure_threshold,
                type(exc).__name__, exc,
            )
            if self._failure_count >= self._failure_threshold:
                self._state = "open"
                self._last_failure_time = time.monotonic()
                logger.error(
                    "Circuit breaker: tripped OPEN after %d consecutive failures (recovery_timeout=%.1fs)",
                    self._failure_count, self._recovery_timeout,
                )
            raise
        else:
            if self._failure_count > 0:
                logger.info("Circuit breaker: success after %d failures, resetting to closed", self._failure_count)
            self._failure_count = 0
            self._state = "closed"
            return result

    def call_sync(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Synchronous entry point for the circuit breaker.

        Used by ``YtDlpWrapper.extract_info_sync`` when the caller is
        already running inside a thread pool and cannot use async/await.

        Args:
            fn: The synchronous callable to execute.
            *args: Positional arguments forwarded to *fn*.
            **kwargs: Keyword arguments forwarded to *fn*.

        Returns:
            The return value of *fn*.

        Raises:
            CircuitBreakerOpenError: If the circuit is open and the recovery
                timeout has not elapsed.
        """
        if self._state == "open":
            if time.monotonic() - self._last_failure_time < self._recovery_timeout:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker is open (sync) (failure_count={self._failure_count})"
                )
            logger.info("Circuit breaker (sync): transitioning open -> half-open (trial)")
            self._state = "half-open"

        try:
            result = fn(*args, **kwargs)
        except CircuitBreakerOpenError:
            raise
        except Exception as exc:
            self._failure_count += 1
            logger.warning(
                "Circuit breaker (sync): call failed (%d/%d): %s: %s",
                self._failure_count, self._failure_threshold,
                type(exc).__name__, exc,
            )
            if self._failure_count >= self._failure_threshold:
                self._state = "open"
                self._last_failure_time = time.monotonic()
                logger.error(
                    "Circuit breaker (sync): tripped OPEN after %d consecutive failures",
                    self._failure_count,
                )
            raise
        else:
            if self._failure_count > 0:
                logger.info("Circuit breaker (sync): success after %d failures, resetting to closed", self._failure_count)
            self._failure_count = 0
            self._state = "closed"
            return result


class YtDlpWrapper:
    """Single entry point for all yt-dlp operations across the application.

    Combines rate limiting, circuit breaking, cookie file management, and
    extractor-args configuration. Use via the ``get_ytdlp_wrapper()``
    global singleton after application startup.
    """

    # Default extraction options used as the base for all calls.
    BASE_OPTS: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "ignoreerrors": True,
        "no_color": True,
        "sleep_interval": 1,
        "max_sleep_interval": 3,
        "retries": 10,
    }

    def __init__(
        self,
        rate_limiter: Optional[YtDlpRateLimiter] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        cookies_file: Optional[str] = None,
        extractor_args: Optional[str] = None,
    ) -> None:
        """Initialize the YtDlpWrapper.

        Args:
            rate_limiter: Rate limiter instance; defaults to YtDlpRateLimiter().
            circuit_breaker: Circuit breaker instance; defaults to CircuitBreaker().
            cookies_file: Path to the cookies file for authenticated requests.
            extractor_args: JSON string of yt-dlp extractor arguments.
        """
        self._rate_limiter = rate_limiter or YtDlpRateLimiter()
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._cookies_file = cookies_file
        self._extractor_args = extractor_args

    # ── Option merging ──

    def _merge_opts(self, opts: dict[str, Any]) -> dict[str, Any]:
        """Merge wrapper-level defaults into *opts* without mutating the original.

        Adds ``cookiefile`` if ``_cookies_file`` is set and the file exists.
        Merges ``extractor_args`` (parsed from JSON) if configured.

        Args:
            opts: The per-call option dictionary.

        Returns:
            A new dict with defaults merged in.
        """
        merged = {**self.BASE_OPTS, **opts}

        # Attach cookie file if configured and present
        if self._cookies_file and os.path.exists(self._cookies_file):
            merged["cookiefile"] = self._cookies_file
        elif self._cookies_file:
            logger.warning("yt-dlp cookie file not found: %s", self._cookies_file)

        # Attach extractor-args from JSON config
        if self._extractor_args:
            try:
                parsed = json.loads(self._extractor_args)
                if isinstance(parsed, dict):
                    # Merge with any existing extractor_args in opts
                    existing = merged.get("extractor_args", {})
                    if isinstance(existing, dict):
                        merged["extractor_args"] = {**existing, **parsed}
                    else:
                        merged["extractor_args"] = parsed
                else:
                    logger.warning("extractor_args is not a dict JSON: %s", type(parsed).__name__)
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse extractor_args JSON: %s", e)

        return merged

    # ── Core extraction ──

    @staticmethod
    def _run_extract(opts: dict[str, Any], url: str, download: bool = False) -> Any:
        """Synchronous yt-dlp extraction.

        Lazy-imports ``yt_dlp.YoutubeDL`` to avoid top-level import cost.

        Args:
            opts: yt-dlp options dict.
            url: The YouTube URL or search query.
            download: Whether to download the video.

        Returns:
            The extraction result dict from yt-dlp.
        """
        from yt_dlp import YoutubeDL

        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=download)

    async def extract_info(
        self, opts: dict[str, Any], url: str, download: bool = False
    ) -> Any:
        """Asynchronous entry point for yt-dlp extraction.

        Merges wrapper-level defaults, acquires the rate limiter, and
        runs through the circuit breaker.

        Args:
            opts: Per-call yt-dlp options (will be merged with BASE_OPTS).
            url: The YouTube URL or search query.
            download: Whether to download the video (default False).

        Returns:
            The extraction result dict from yt-dlp.

        Raises:
            CircuitBreakerOpenError: If the circuit breaker is open.
        """
        merged = self._merge_opts(opts)
        async with self._rate_limiter:
            return await self._circuit_breaker.call(self._run_extract, merged, url, download)

    def extract_info_sync(
        self, opts: dict[str, Any], url: str, download: bool = False
    ) -> Any:
        """Synchronous entry point for yt-dlp extraction.

        For use when the caller is already inside a thread pool (e.g. the
        existing ``*_sync`` methods in YoutubeService). Merges wrapper-level
        defaults and runs through the circuit breaker.

        Note: The rate limiter is NOT applied in the sync path because sync
        callers are already expected to be running with bounded concurrency
        via their own thread pool. The circuit breaker still protects against
        cascading failures.

        Args:
            opts: Per-call yt-dlp options (will be merged with BASE_OPTS).
            url: The YouTube URL or search query.
            download: Whether to download the video.

        Returns:
            The extraction result dict from yt-dlp.

        Raises:
            CircuitBreakerOpenError: If the circuit breaker is open.
        """
        merged = self._merge_opts(opts)
        return self._circuit_breaker.call_sync(self._run_extract, merged, url, download)

    # ── Convenience methods (async) ──

    async def search(
        self, query: str, max_results: int = 20, extract_flat: bool = True
    ) -> list[dict[str, Any]]:
        """Search YouTube videos by keyword.

        Args:
            query: The search query string.
            max_results: Maximum number of results to return (default 20).
            extract_flat: If True, return flat entries (faster, less detail).

        Returns:
            List of raw extraction entry dicts.
        """
        opts: dict[str, Any] = {
            "extract_flat": "in_playlist" if extract_flat else False,
        }
        search_query = f"ytsearch{max_results}:{query}"
        result = await self.extract_info(opts, search_query)
        entries = result.get("entries") or []
        return [e for e in entries if e]

    def search_sync(
        self, query: str, max_results: int = 20, extract_flat: bool = True
    ) -> list[dict[str, Any]]:
        """Synchronous version of :meth:`search`."""
        opts: dict[str, Any] = {
            "extract_flat": "in_playlist" if extract_flat else False,
        }
        search_query = f"ytsearch{max_results}:{query}"
        result = self.extract_info_sync(opts, search_query)
        entries = result.get("entries") or []
        return [e for e in entries if e]

    async def get_channel_videos(
        self, channel_url: str, max_results: int = 50, extract_flat: bool = True
    ) -> list[dict[str, Any]]:
        """Get videos from a YouTube channel.

        Args:
            channel_url: The channel URL (e.g. ``https://www.youtube.com/@channel``).
            max_results: Maximum number of videos to return.
            extract_flat: If True, return flat entries (faster).

        Returns:
            List of raw extraction entry dicts.
        """
        opts: dict[str, Any] = {
            "extract_flat": "in_playlist" if extract_flat else False,
        }
        result = await self.extract_info(opts, channel_url)
        entries = result.get("entries") or []
        return [e for e in entries if e][:max_results]

    def get_channel_videos_sync(
        self, channel_url: str, max_results: int = 50, extract_flat: bool = True
    ) -> list[dict[str, Any]]:
        """Synchronous version of :meth:`get_channel_videos`."""
        opts: dict[str, Any] = {
            "extract_flat": "in_playlist" if extract_flat else False,
        }
        result = self.extract_info_sync(opts, channel_url)
        entries = result.get("entries") or []
        return [e for e in entries if e][:max_results]

    async def get_video_info(self, url: str) -> Optional[dict[str, Any]]:
        """Get full metadata for a single video.

        Args:
            url: The YouTube video URL.

        Returns:
            Full extraction result dict, or None on failure.
        """
        opts: dict[str, Any] = {
            "extract_flat": False,
        }
        try:
            return await self.extract_info(opts, url)
        except Exception as e:
            logger.error("yt-dlp get_video_info failed: %s", e)
            return None

    def get_video_info_sync(self, url: str) -> Optional[dict[str, Any]]:
        """Synchronous version of :meth:`get_video_info`."""
        opts: dict[str, Any] = {
            "extract_flat": False,
        }
        try:
            return self.extract_info_sync(opts, url)
        except Exception as e:
            logger.error("yt-dlp get_video_info_sync failed: %s", e)
            return None


# ── Global singleton accessors ──

_wrapper_instance: Optional[YtDlpWrapper] = None


def get_ytdlp_wrapper() -> YtDlpWrapper:
    """Return the global YtDlpWrapper singleton.

    Creates a default instance on first call if not already set.
    """
    global _wrapper_instance
    if _wrapper_instance is None:
        _wrapper_instance = YtDlpWrapper()
    return _wrapper_instance


def set_ytdlp_wrapper(wrapper: Optional[YtDlpWrapper]) -> None:
    """Set the global YtDlpWrapper singleton.

    Used during application startup and in tests for injection.
    Pass ``None`` to reset.
    """
    global _wrapper_instance
    _wrapper_instance = wrapper
