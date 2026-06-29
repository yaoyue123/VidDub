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
