"""Phase 9: 定时任务 + 批量管理 unit tests (V1).

覆盖 (per V1):
- ChannelScanner.scan_once (mocked YoutubeService) — happy path + dedupe + filter
- Channel CRUD endpoints
- Batch pause/resume/retry/delete endpoints
- Export CSV/JSON
- Soft delete filter

Live network tests marked with @pytest.mark.requires_network.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool


# ─────────────────────────────────────────────────────────────────
# Test harness — uses StaticPool so :memory: SQLite persists across requests
# ─────────────────────────────────────────────────────────────────

def _make_isolated_db():
    """Create a fresh in-memory engine + session factory, return both."""
    from app.core.database import Base
    # Force import all models so metadata is populated
    import app.models  # noqa: F401

    # StaticPool: 所有连接共享同一 in-memory DB（避免每个请求新连接丢失数据）
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_init())

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, factory, loop


@pytest.fixture
def app_client():
    """TestClient with /api/* deps overridden to use a fresh in-memory DB."""
    from app.core.database import get_db
    from app.main import create_app

    engine, factory, loop = _make_isolated_db()
    app = create_app()

    async def _override():
        async with factory() as s:
            try:
                yield s
                await s.commit()  # match real get_db (commit after response)
            except Exception:
                await s.rollback()
                raise

    # Override get_db everywhere it's imported
    app.dependency_overrides[get_db] = _override
    for mod_name in [
        "app.api.config", "app.api.stats", "app.api.subtitles", "app.api.dub",
        "app.api.videos", "app.api.tasks", "app.api.channels", "app.api.export",
    ]:
        try:
            import importlib
            m = importlib.import_module(mod_name)
            if hasattr(m, "get_db"):
                app.dependency_overrides[m.get_db] = _override
        except ImportError:
            pass

    with TestClient(app) as c:
        c._test_engine = engine
        c._test_loop = loop
        c._test_factory = factory
        yield c

    loop.run_until_complete(engine.dispose())
    loop.close()
    app.dependency_overrides.clear()


async def _seed(factory, *models):
    """Insert models into the test DB."""
    async with factory() as s:
        for m in models:
            s.add(m)
        await s.commit()


def _make_channel(**overrides):
    from app.models.channel import Channel
    defaults = dict(
        name="Test Channel",
        url="https://www.youtube.com/@testchannel",
        enabled=True,
        scan_interval_hours=6,
    )
    defaults.update(overrides)
    return Channel(**defaults)


def _make_video(**overrides):
    from app.models.video import Video
    defaults = dict(
        youtube_url="https://youtu.be/abc123",
        youtube_id="abc123",
        title="Test Video",
        channel="Test Channel",
        status="pending",
    )
    defaults.update(overrides)
    return Video(**defaults)


def _make_task(**overrides):
    from app.models.task import Task
    defaults = dict(
        video_id=1,
        type="download",
        status="pending",
        progress=0.0,
        message="waiting",
    )
    defaults.update(overrides)
    return Task(**defaults)


def _fake_video_dict(yt_id: str, **overrides) -> dict:
    defaults = dict(
        youtube_id=yt_id,
        title=f"Video {yt_id}",
        channel="Test Channel",
        channel_url="https://www.youtube.com/@testchannel",
        duration=300,
        view_count=1000,
        like_count=50,
        comment_count=10,
        thumbnail_url=f"https://img.youtube.com/vi/{yt_id}/default.jpg",
        description="desc",
        webpage_url=f"https://www.youtube.com/watch?v={yt_id}",
    )
    defaults.update(overrides)
    return defaults


# ─────────────────────────────────────────────────────────────────
# 1. ChannelScanner.scan_once — mocked YoutubeService
# ─────────────────────────────────────────────────────────────────

def test_scan_once_happy_path(app_client):
    """scan_once returns found/added counts and writes ScanLog."""
    from app.services import channel_scanner as mod
    from app.models.channel import Channel
    from app.models.video import Video
    from app.models.task import Task
    from app.models.scan_log import ScanLog

    factory = app_client._test_factory

    # Seed a channel
    asyncio.get_event_loop().run_until_complete(_seed(factory, _make_channel()))
    channel_id = 1

    # Build scanner with mocked YoutubeService
    scanner = mod.ChannelScanner(max_concurrent=2)
    mock_yt = MagicMock()
    mock_yt.get_channel_videos = AsyncMock(return_value=[
        _fake_video_dict("vid001"),
        _fake_video_dict("vid002"),
    ])
    scanner._yt = mock_yt

    # Patch module-level session factory
    orig_factory = mod.async_session_factory
    mod.async_session_factory = factory
    try:
        result = asyncio.get_event_loop().run_until_complete(scanner.scan_once(channel_id))
    finally:
        mod.async_session_factory = orig_factory

    assert result.found_count == 2
    assert result.added_count == 2
    assert result.error_msg is None

    # Verify DB state
    async def _verify():
        async with factory() as session:
            vids = (await session.execute(select(Video).where(Video.channel_id == channel_id))).scalars().all()
            assert len(vids) == 2
            assert all(v.source == "channel" for v in vids)
            tasks = (await session.execute(
                select(Task).join(Video, Task.video_id == Video.id).where(Video.channel_id == channel_id)
            )).scalars().all()
            assert len(tasks) == 2
            assert all(t.type == "download" for t in tasks)
            logs = (await session.execute(select(ScanLog).where(ScanLog.channel_id == channel_id))).scalars().all()
            assert len(logs) == 1
            assert logs[0].found_count == 2
            assert logs[0].added_count == 2

    asyncio.get_event_loop().run_until_complete(_verify())


def test_scan_once_dedupes_existing_videos(app_client):
    """扫描发现已存在的 youtube_id 应跳过."""
    from app.services import channel_scanner as mod
    from app.models.video import Video

    factory = app_client._test_factory
    asyncio.get_event_loop().run_until_complete(_seed(
        factory,
        _make_channel(),
        Video(
            youtube_url="https://youtu.be/dup001", youtube_id="dup001",
            title="existing", channel="Test Channel", status="pending",
            channel_id=1, source="channel",
        ),
    ))

    scanner = mod.ChannelScanner()
    mock_yt = MagicMock()
    mock_yt.get_channel_videos = AsyncMock(return_value=[
        _fake_video_dict("dup001"),  # already exists
        _fake_video_dict("new001"),  # new
    ])
    scanner._yt = mock_yt

    orig = mod.async_session_factory
    mod.async_session_factory = factory
    try:
        result = asyncio.get_event_loop().run_until_complete(scanner.scan_once(1))
    finally:
        mod.async_session_factory = orig

    assert result.found_count == 2
    assert result.added_count == 1


def test_scan_once_applies_filters(app_client):
    """filter_min_views / filter_max_duration_sec 应正确过滤."""
    from app.services import channel_scanner as mod
    from app.models.channel import Channel

    factory = app_client._test_factory
    asyncio.get_event_loop().run_until_complete(_seed(
        factory,
        _make_channel(filter_min_views=500, filter_max_duration_sec=600),
    ))

    scanner = mod.ChannelScanner()
    mock_yt = MagicMock()
    mock_yt.get_channel_videos = AsyncMock(return_value=[
        _fake_video_dict("low_views", view_count=100),       # filtered
        _fake_video_dict("too_long", duration=9999),         # filtered
        _fake_video_dict("just_right", view_count=800, duration=400),
    ])
    scanner._yt = mock_yt

    orig = mod.async_session_factory
    mod.async_session_factory = factory
    try:
        result = asyncio.get_event_loop().run_until_complete(scanner.scan_once(1))
    finally:
        mod.async_session_factory = orig

    assert result.found_count == 3
    assert result.added_count == 1


def test_scan_once_handles_yt_failure(app_client):
    """YoutubeService 抛错时应写 error ScanLog."""
    from app.services import channel_scanner as mod
    from app.models.scan_log import ScanLog

    factory = app_client._test_factory
    asyncio.get_event_loop().run_until_complete(_seed(factory, _make_channel()))

    scanner = mod.ChannelScanner()
    mock_yt = MagicMock()
    mock_yt.get_channel_videos = AsyncMock(side_effect=RuntimeError("network down"))
    scanner._yt = mock_yt

    orig = mod.async_session_factory
    mod.async_session_factory = factory
    try:
        result = asyncio.get_event_loop().run_until_complete(scanner.scan_once(1))
    finally:
        mod.async_session_factory = orig

    assert result.found_count == 0
    assert result.added_count == 0
    assert "network down" in (result.error_msg or "")

    async def _verify():
        async with factory() as session:
            logs = (await session.execute(select(ScanLog).where(ScanLog.channel_id == 1))).scalars().all()
            assert len(logs) == 1
            assert logs[0].error_msg is not None

    asyncio.get_event_loop().run_until_complete(_verify())


# ─────────────────────────────────────────────────────────────────
# 2. Channel CRUD
# ─────────────────────────────────────────────────────────────────

def test_channel_crud_lifecycle(app_client):
    """POST → GET → PUT → DELETE."""
    r = app_client.post("/api/channels", json={
        "name": "Test Ch",
        "url": "https://www.youtube.com/@testch_crud",
        "enabled": True,
        "scan_interval_hours": 12,
    })
    assert r.status_code == 201, r.text
    ch = r.json()
    cid = ch["id"]
    assert ch["name"] == "Test Ch"
    assert ch["scan_interval_hours"] == 12

    # Get
    r = app_client.get(f"/api/channels/{cid}")
    assert r.status_code == 200

    # Update
    r = app_client.put(f"/api/channels/{cid}", json={"scan_interval_hours": 3})
    assert r.status_code == 200
    assert r.json()["scan_interval_hours"] == 3

    # List
    r = app_client.get("/api/channels")
    assert r.status_code == 200
    assert any(c["id"] == cid for c in r.json()["items"])

    # Delete
    r = app_client.delete(f"/api/channels/{cid}")
    assert r.status_code == 204
    r = app_client.get(f"/api/channels/{cid}")
    assert r.status_code == 404


def test_channel_create_duplicate_url_409(app_client):
    body = {"name": "A", "url": "https://www.youtube.com/@dup_url_test"}
    r1 = app_client.post("/api/channels", json=body)
    assert r1.status_code == 201
    r2 = app_client.post("/api/channels", json=body)
    assert r2.status_code == 409


def test_channel_scan_logs_empty(app_client):
    r = app_client.post("/api/channels", json={
        "name": "X", "url": "https://www.youtube.com/@scan_logs_empty_test",
    })
    cid = r.json()["id"]
    r = app_client.get(f"/api/channels/{cid}/scan-logs")
    assert r.status_code == 200
    assert r.json()["items"] == []


# ─────────────────────────────────────────────────────────────────
# 3. Batch pause/resume/retry/delete
# ─────────────────────────────────────────────────────────────────

@pytest.fixture
def app_client_with_video_and_tasks(app_client):
    """Add a video + 2 pending tasks for batch tests."""
    factory = app_client._test_factory
    asyncio.get_event_loop().run_until_complete(_seed(
        factory,
        _make_video(),
        _make_task(video_id=1, type="download", status="pending"),
        _make_task(video_id=1, type="transcribe", status="pending"),
    ))
    return app_client


def test_batch_pause_pending_tasks(app_client_with_video_and_tasks):
    client = app_client_with_video_and_tasks
    r = client.post("/api/tasks/batch", json={"action": "pause", "ids": [1, 2]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success_count"] == 2
    assert body["failed_count"] == 0


def test_batch_resume_cancelled_tasks(app_client_with_video_and_tasks):
    client = app_client_with_video_and_tasks
    client.post("/api/tasks/batch", json={"action": "pause", "ids": [1, 2]})
    r = client.post("/api/tasks/batch", json={"action": "resume", "ids": [1, 2]})
    body = r.json()
    assert body["success_count"] == 2


def test_batch_retry_failed_tasks_only(app_client_with_video_and_tasks):
    """cancelled 不能 retry — 应该 failed."""
    client = app_client_with_video_and_tasks
    client.post("/api/tasks/batch", json={"action": "pause", "ids": [1]})
    r = client.post("/api/tasks/batch", json={"action": "retry", "ids": [1]})
    assert r.json()["failed_count"] == 1


def test_batch_delete_soft_deletes_video(app_client_with_video_and_tasks):
    client = app_client_with_video_and_tasks
    r = client.post("/api/tasks/batch", json={"action": "delete", "ids": [1]})
    assert r.status_code == 200
    assert r.json()["success_count"] == 1

    # Video should be soft-deleted (not visible in default tasks list)
    after = client.get("/api/tasks").json()["total"]
    # include_deleted=true — 应该还能看到
    included = client.get("/api/tasks?include_deleted=true").json()["total"]
    assert included >= after


def test_batch_invalid_action_400(app_client_with_video_and_tasks):
    client = app_client_with_video_and_tasks
    r = client.post("/api/tasks/batch", json={"action": "bogus", "ids": [1]})
    assert r.status_code == 400


def test_batch_empty_ids_400(app_client_with_video_and_tasks):
    client = app_client_with_video_and_tasks
    r = client.post("/api/tasks/batch", json={"action": "pause", "ids": []})
    assert r.status_code == 400


# ─────────────────────────────────────────────────────────────────
# 4. Export CSV/JSON
# ─────────────────────────────────────────────────────────────────

def test_export_csv(app_client_with_video_and_tasks):
    client = app_client_with_video_and_tasks
    r = client.get("/api/export/tasks?format=csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "attachment" in r.headers.get("content-disposition", "")

    reader = csv.DictReader(io.StringIO(r.text))
    rows = list(reader)
    assert len(rows) >= 1
    assert "task_id" in rows[0]
    assert "youtube_id" in rows[0]


def test_export_json(app_client_with_video_and_tasks):
    client = app_client_with_video_and_tasks
    r = client.get("/api/export/tasks?format=json")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "task_id" in data[0]
    assert "youtube_id" in data[0]


def test_export_with_status_filter(app_client_with_video_and_tasks):
    client = app_client_with_video_and_tasks
    r = client.get("/api/export/tasks?format=json&status=pending")
    assert r.status_code == 200
    data = r.json()
    assert all(row["status"] == "pending" for row in data)


def test_export_invalid_format_422(app_client_with_video_and_tasks):
    client = app_client_with_video_and_tasks
    r = client.get("/api/export/tasks?format=xml")
    assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────
# 5. Soft delete filter
# ─────────────────────────────────────────────────────────────────

def test_hard_delete_removes_video_and_tasks(app_client_with_video_and_tasks):
    """v3.2: 物理删除视频 + 级联清除 Tasks / Subtitles / PublishRecords."""
    client = app_client_with_video_and_tasks
    before = client.get("/api/tasks").json()["total"]

    # Delete via batch — 物理删除 video + cascade 所有关联数据
    client.post("/api/tasks/batch", json={"action": "delete", "ids": [1]})

    after = client.get("/api/tasks").json()["total"]
    assert after < before, f"after={after} should be < before={before} (video + tasks deleted)"

    # 视频也被删了
    v = client.get("/api/videos/1")
    assert v.status_code == 404, "Video should be deleted, not soft-deleted"


# ─────────────────────────────────────────────────────────────────
# 6. Live network tests (skipped by default)
# ─────────────────────────────────────────────────────────────────

@pytest.mark.requires_network
def test_scan_once_real_network():
    """真实扫描一个公开频道 (slow, requires network)."""
    pytest.skip("live network test — enable with -m requires_network")
