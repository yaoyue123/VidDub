"""Phase 5 endpoint smoke tests.

Uses a per-test in-memory SQLite DB via FastAPI dependency_overrides.

Covers:
- PUT /api/config/{key} (single update)
- POST /api/config/test-siliconflow (no key + mocked HTTP)
- GET /api/stats/dashboard (empty DB)
- GET /api/dub/{id}/preview/{kind} (422 + 404)
- POST /api/subtitles/{video_id}/retranslate (404 + 422 paths)
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _make_isolated_db():
    """Create a fresh in-memory engine + session factory, return both."""
    from app.core.database import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_init())

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, factory, loop


@pytest.fixture
def app_client():
    """TestClient with all /api/* get_db deps overridden to use a fresh in-memory DB."""
    from app.core.database import get_db
    from app.main import create_app

    engine, factory, loop = _make_isolated_db()
    app = create_app()

    async def _override():
        async with factory() as s:
            yield s

    # Override on every place get_db is imported
    app.dependency_overrides[get_db] = _override
    # Also override on import-path symbols if different
    for mod in [
        "app.api.config",
        "app.api.stats",
        "app.api.subtitles",
        "app.api.dub",
        "app.api.videos",
        "app.api.tasks",
    ]:
        try:
            import importlib
            m = importlib.import_module(mod)
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


# ── 1. PUT /api/config/{key} ──

def test_update_single_config_creates_then_updates(app_client):
    r = app_client.put("/api/config/test_phase5_key", json={"value": "hello"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["key"] == "test_phase5_key"
    assert body["value"] == "hello"

    r2 = app_client.put("/api/config/test_phase5_key", json={"value": "world"})
    assert r2.status_code == 200
    assert r2.json()["value"] == "world"


# ── 2. POST /api/config/test-siliconflow ──

def test_test_siliconflow_no_api_key(app_client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.siliconflow_api_key", "")
    r = app_client.post("/api/config/test-siliconflow")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "API Key" in body["error"] or "未配置" in body["error"]


def test_test_siliconflow_with_mocked_httpx(app_client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.siliconflow_api_key", "sk-fake-test-key")

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.text = '{"choices":[{"message":{"content":"ok"}}]}'

    fake_client = AsyncMock()
    fake_client.post.return_value = fake_resp
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = None

    with patch("app.api.config.httpx.AsyncClient", return_value=fake_client):
        r = app_client.post("/api/config/test-siliconflow")

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["latency_ms"] >= 0


def test_test_siliconflow_401(app_client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.siliconflow_api_key", "sk-invalid")

    fake_resp = MagicMock()
    fake_resp.status_code = 401
    fake_resp.text = "unauthorized"

    fake_client = AsyncMock()
    fake_client.post.return_value = fake_resp
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = None

    with patch("app.api.config.httpx.AsyncClient", return_value=fake_client):
        r = app_client.post("/api/config/test-siliconflow")

    body = r.json()
    assert body["ok"] is False
    assert "401" in body["error"] or "无效" in body["error"]


# ── 3. GET /api/stats/dashboard ──

def test_dashboard_empty_db(app_client):
    r = app_client.get("/api/stats/dashboard")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["today_count"] == 0
    assert body["success_rate"] == 0.0
    assert body["avg_duration_sec"] is None
    assert body["recent_tasks"] == []
    assert body["failed_tasks"] == []


# ── 4. GET /api/dub/{id}/preview/{kind} ──

def test_preview_invalid_kind(app_client):
    from app.models.video import Video
    asyncio.get_event_loop().run_until_complete(
        _seed(app_client._test_factory, Video(
            youtube_url="https://youtu.be/x", youtube_id="x",
            title="t", channel="c", status="completed",
        ))
    )
    r = app_client.get("/api/dub/1/preview/bogus")
    assert r.status_code == 422


def test_preview_video_not_found(app_client):
    r = app_client.get("/api/dub/9999/preview/dubbing")
    assert r.status_code == 404


def test_preview_missing_file(app_client, tmp_path):
    from app.models.video import Video
    from app.models.config import Config

    asyncio.get_event_loop().run_until_complete(
        _seed(
            app_client._test_factory,
            Video(
                youtube_url="https://youtu.be/x", youtube_id="x",
                title="t", channel="c", status="completed",
            ),
            Config(key="download_dir", value=str(tmp_path), description="test"),
        )
    )
    r = app_client.get("/api/dub/1/preview/dubbing")
    assert r.status_code == 404


# ── 5. POST /api/subtitles/{video_id}/retranslate ──

def test_retranslate_video_not_found(app_client):
    r = app_client.post("/api/subtitles/9999/retranslate?segment_index=0")
    assert r.status_code == 404


def test_retranslate_translated_json_missing(app_client, tmp_path):
    from app.models.video import Video
    from app.models.config import Config

    asyncio.get_event_loop().run_until_complete(
        _seed(
            app_client._test_factory,
            Video(
                youtube_url="https://youtu.be/x", youtube_id="x",
                title="t", channel="c", status="completed",
            ),
            Config(key="download_dir", value=str(tmp_path), description="test"),
        )
    )
    r = app_client.post("/api/subtitles/1/retranslate?segment_index=0")
    assert r.status_code == 404
    assert "translated.json" in r.json()["detail"]


def test_retranslate_out_of_range(app_client, tmp_path):
    from app.models.video import Video
    from app.models.config import Config

    video_dir = tmp_path / "1"
    video_dir.mkdir()
    with open(video_dir / "translated.json", "w", encoding="utf-8") as f:
        json.dump(
            [{"id": 0, "start": 0, "end": 1, "text": "hi", "text_zh": "你好"}],
            f,
        )

    asyncio.get_event_loop().run_until_complete(
        _seed(
            app_client._test_factory,
            Video(
                youtube_url="https://youtu.be/x", youtube_id="x",
                title="t", channel="c", status="completed",
            ),
            Config(key="download_dir", value=str(tmp_path), description="test"),
        )
    )
    r = app_client.post("/api/subtitles/1/retranslate?segment_index=5")
    assert r.status_code == 422
    assert "越界" in r.json()["detail"]
