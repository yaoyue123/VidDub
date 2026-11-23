"""yt-dlp proxy / cookie option propagation."""
import asyncio

import pytest

from app.services.ytdlp_wrapper import YtDlpRateLimiter, YtDlpWrapper
from app.services.youtube import YoutubeService


@pytest.mark.asyncio
async def test_rate_limiter_releases_semaphore():
    """__aexit__ must release the semaphore, or later calls block forever."""
    limiter = YtDlpRateLimiter(min_interval=0, max_concurrent=1)
    async with limiter:
        pass
    # If the slot leaked, this acquire never completes.
    await asyncio.wait_for(limiter.acquire(), timeout=1)
    await limiter.release()


@pytest.mark.asyncio
async def test_progress_hook_does_not_use_create_task(monkeypatch):
    """yt-dlp calls the hook from a worker thread; schedule on the main loop."""
    from app.services import scheduler

    scheduled = []

    def fake_submit(coro, loop):
        scheduled.append(coro)
        coro.close()

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", fake_submit)

    hook = scheduler._make_progress_hook(1, 1, db_session_factory=None)
    hook({"status": "downloading", "total_bytes": 100, "downloaded_bytes": 50})
    assert scheduled, "progress hook should schedule DB/WS updates"


def test_apply_network_opts_includes_proxy_and_cookie(tmp_path):
    cookie = tmp_path / "cookies.txt"
    cookie.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    wrapper = YtDlpWrapper(
        cookies_file=str(cookie),
        proxy="http://127.0.0.1:7890",
        extractor_args='{"youtube": {"player_client": ["web"]}}',
    )
    opts = wrapper.apply_network_opts({"format": "best"})

    assert opts["proxy"] == "http://127.0.0.1:7890"
    assert opts["cookiefile"] == str(cookie)
    assert opts["extractor_args"]["youtube"]["player_client"] == ["web"]
    # Download opts must not inherit extraction-only defaults.
    assert "skip_download" not in opts


def test_download_sync_passes_proxy_to_ytdlp(tmp_path, monkeypatch):
    captured: dict = {}

    class FakeYDL:
        def __init__(self, opts):
            captured.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=True):
            return None

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDL)

    svc = YoutubeService(
        download_dir=str(tmp_path),
        ytdlp_wrapper=YtDlpWrapper(proxy="http://127.0.0.1:7890"),
    )
    assert svc.download_sync("https://youtu.be/example") is None
    assert captured["proxy"] == "http://127.0.0.1:7890"
    assert captured["format"].startswith("bestvideo")
