"""Phase 7 平台自动发布 unit tests.

覆盖范围 (V1)：
- PublishRecord 模型 CRUD
- BilibiliPublisher (mocked Playwright)
- IxiguaPublisher (mocked Playwright)
- PublishManager 编排 (mocked 两个 publisher)
- title_translate (mocked SiliconFlow)
- publish API endpoints (mocked services)

Playwright-required tests 用 @pytest.mark.requires_playwright 标记.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────
# PublishRecord 模型 (B2)
# ─────────────────────────────────────────────────────────────────

def test_publish_record_model_basic_fields():
    """模型字段 / 默认值验证 — 仅断言可构造 + 关键字段映射."""
    from app.models.publish_record import PublishRecord, PublishStatus, PublishPlatform
    r = PublishRecord(
        video_id=1,
        platform=PublishPlatform.BILIBILI,
        status=PublishStatus.PENDING,
        needs_relogin=False,
        retry_count=0,
    )
    assert r.platform == "bilibili"
    assert r.status == "pending"
    assert r.platform_video_url is None


def test_publish_status_constants():
    from app.models.publish_record import PublishStatus
    assert PublishStatus.PENDING == "pending"
    assert PublishStatus.PUBLISHING == "publishing"
    assert PublishStatus.PUBLISHED == "published"
    assert PublishStatus.FAILED == "failed"


def test_publish_platform_constants():
    from app.models.publish_record import PublishPlatform
    assert PublishPlatform.DOUYIN == "douyin"
    assert PublishPlatform.BILIBILI == "bilibili"
    assert PublishPlatform.KUAISHOU == "kuaishou"
    assert PublishPlatform.TENCENT == "tencent"
    assert PublishPlatform.XIAOHONGSHU == "xiaohongshu"


# ─────────────────────────────────────────────────────────────────
# Base 类
# ─────────────────────────────────────────────────────────────────

def test_publish_fields_dataclass():
    from app.services.publish.base import PublishFields
    f = PublishFields(title="测试标题", description="描述", tags=["t1", "t2"])
    assert f.title == "测试标题"
    assert f.tags == ["t1", "t2"]
    assert f.cover_path is None
    assert f.copyright_type is None


def test_publish_result_dataclass():
    from app.services.publish.base import PublishResult
    r = PublishResult(success=True, platform_video_url="https://example.com/v/1")
    assert r.success is True
    assert r.error_msg is None
    assert r.needs_relogin is False


def test_safe_text_truncation():
    from app.services.publish.base import PlatformPublisher
    assert PlatformPublisher._safe_text("abc", 5) == "abc"
    assert PlatformPublisher._safe_text("abcdef", 3) == "abc"
    assert PlatformPublisher._safe_text("", 10) == ""


# ─────────────────────────────────────────────────────────────────
# IxiguaPublisher — mocked
# ─────────────────────────────────────────────────────────────────

@pytest.fixture
def ixigua_state_file(tmp_path):
    state = {
        "platform": "ixigua",
        "saved_at": 1234567890,
        "cookies": {"sessionid": "abc"},
        "user_info": {"uid": 99},
    }
    p = tmp_path / "ixigua_storage_state.json"
    p.write_text(json.dumps(state), encoding="utf-8")
    return str(p)


@pytest.mark.asyncio
async def test_ixigua_validate_login(ixigua_state_file):
    from app.services.publish.ixigua import IxiguaPublisher
    pub = IxiguaPublisher(storage_state_path=ixigua_state_file)
    with patch("app.services.platform.manager.get_login_manager") as gm:
        login = MagicMock()
        login.check_login_status = AsyncMock(return_value=True)
        gm.return_value.get.return_value = login
        assert await pub.validate_login() is True


@pytest.mark.asyncio
async def test_ixigua_publish_missing_video(ixigua_state_file):
    from app.services.publish.ixigua import IxiguaPublisher
    from app.services.publish.base import PublishFields
    pub = IxiguaPublisher(storage_state_path=ixigua_state_file)
    result = await pub.publish(video_id=1,
                                fields=PublishFields(title="t"),
                                video_file_path="/nonexistent.mp4")
    assert result.success is False


@pytest.mark.asyncio
async def test_ixigua_load_storage_state_for_playwright(ixigua_state_file):
    from app.services.publish.ixigua import IxiguaPublisher
    pub = IxiguaPublisher(storage_state_path=ixigua_state_file)
    state = pub._load_storage_state_for_playwright()
    assert state is not None
    assert state["cookies"][0]["domain"] == ".ixigua.com"


# ─────────────────────────────────────────────────────────────────
# PublishManager — mocked publishers
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_manager_get_returns_publisher():
    from app.services.publish.manager import PublishManager
    from app.services.publish.base import PlatformPublisher
    pm = PublishManager()

    # patch 内部 import: from app.services.platform.manager import get_login_manager
    with patch("app.services.platform.manager.get_login_manager") as glm:
        lm = MagicMock()
        lm.storage_state_path.return_value = "/tmp/state.json"
        glm.return_value = lm
        p = pm.get("bilibili")
        assert isinstance(p, PlatformPublisher)
        assert p.platform == "bilibili"

        p2 = pm.get("ixigua")
        assert p2.platform == "ixigua"

        # cache
        assert pm.get("bilibili") is p


def test_publish_manager_unsupported():
    from app.services.publish.manager import PublishManager
    pm = PublishManager()
    with pytest.raises(ValueError, match="Unsupported"):
        pm.get("youtube")


# ─────────────────────────────────────────────────────────────────
# title_translate (B9) — mocked SiliconFlow
# ─────────────────────────────────────────────────────────────────

def test_parse_translate_response_json():
    from app.services.publish.title_translate import _parse_translate_response
    t, d, tags = _parse_translate_response(
        '{"title":"标题","description":"描述","tags":["标签1","标签2"]}'
    )
    assert t == "标题"
    assert d == "描述"
    assert tags == ["标签1", "标签2"]


def test_parse_translate_response_with_code_fence():
    from app.services.publish.title_translate import _parse_translate_response
    t, _, tags = _parse_translate_response(
        '```json\n{"title":"T","description":"","tags":["a"]}\n```'
    )
    assert t == "T"
    assert tags == ["a"]


def test_parse_translate_response_invalid():
    from app.services.publish.title_translate import _parse_translate_response
    t, d, tags = _parse_translate_response("not json at all")
    assert t == ""
    assert d == ""
    assert tags == []


def test_find_thumbnail_path_nonexistent():
    from app.services.publish.title_translate import _find_thumbnail_path
    assert _find_thumbnail_path(99999, None) is None


@pytest.mark.asyncio
async def test_prepare_publish_fields_translates_title(monkeypatch):
    """用 mock SiliconFlow client 测试字段生成."""
    import app.services.publish.title_translate as tt

    async def fake_translate(en_title, en_desc, configs):
        return ("中文标题", "中文描述", ["tag1", "tag2"])

    monkeypatch.setattr(tt, "_translate_via_siliconflow", fake_translate)

    # 模拟 async_session_factory (函数内部 from app.core.database import async_session_factory)
    v = MagicMock()
    v.id = 1
    v.title = "English Title"
    v.description = "English description"
    # Phase 8 新增字段 — 显式 None 避免被 MagicMock 真值误判
    v.title_chosen = None
    v.tags_chosen = None
    v.thumbnail_url = None
    v.youtube_url = "https://youtu.be/abc"

    cfg1 = MagicMock()
    cfg1.key = "publish_default_tags"
    cfg1.value = "搬运,英语学习"
    cfg2 = MagicMock()
    cfg2.key = "bilibili_default_category"
    cfg2.value = "122"
    cfg3 = MagicMock()
    cfg3.key = "ixigua_default_copyright"
    cfg3.value = "repost"

    class _MockSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def execute(self, q):
            result = MagicMock()
            # 视频查询 vs config 查询；都返回不同
            # 通过 select model 区分 — 简化：第一次是 Video，之后是 Config
            calls = [0]
            def scalars_all():
                return [cfg1, cfg2, cfg3]
            def scalars_one():
                return v
            # 用一个简单的"第几次调用"区分
            _MockSession._calls = getattr(_MockSession, "_calls", 0) + 1
            if _MockSession._calls == 1:
                result.scalar_one_or_none = lambda: v
            else:
                m = MagicMock()
                m.all = lambda: [cfg1, cfg2, cfg3]
                result.scalars = lambda: m
            return result
        def scalars(self):
            return None
        async def close(self): pass

    def fake_factory():
        return _MockSession()

    # patch core.database.async_session_factory
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "async_session_factory", fake_factory)

    fields = await tt.prepare_publish_fields(1)
    assert fields.title == "中文标题"
    assert "tag1" in fields.tags
    assert fields.copyright_type in ("original", "repost")


# ─────────────────────────────────────────────────────────────────
# API endpoints (B10) — 用 TestClient
# ─────────────────────────────────────────────────────────────────

@pytest.fixture
def publish_api_client(tmp_path):
    """FastAPI sync TestClient with in-memory sqlite DB."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # 用 sync engine 创建 schema
    test_db_path = tmp_path / "test.db"
    sync_engine = create_engine(f"sqlite:///{test_db_path}", echo=False)
    from app.models.base import Base
    Base.metadata.create_all(sync_engine)

    # override async db
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{test_db_path}")
    TestSessionFactory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def get_test_db():
        async with TestSessionFactory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    from app.main import app
    from app.core.database import get_db
    app.dependency_overrides[get_db] = get_test_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    import asyncio as _aio
    _aio.get_event_loop().run_until_complete(test_engine.dispose())


def test_publish_api_list_records_empty(publish_api_client):
    res = publish_api_client.get("/api/publish/records")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_publish_api_get_record_404(publish_api_client):
    res = publish_api_client.get("/api/publish/records/9999")
    assert res.status_code == 404


def test_publish_api_trigger_video_not_found(publish_api_client):
    res = publish_api_client.post("/api/publish/9999/bilibili")
    assert res.status_code == 404


def test_publish_api_trigger_invalid_platform(publish_api_client):
    res = publish_api_client.post("/api/publish/1/youtube")
    assert res.status_code == 404


def test_publish_api_retry_record_not_found(publish_api_client):
    res = publish_api_client.post("/api/publish/records/9999/retry")
    assert res.status_code == 404


def test_publish_api_records_filter_by_platform(publish_api_client):
    """Filter by invalid platform should 404."""
    res = publish_api_client.get("/api/publish/records", params={"platform": "youtube"})
    assert res.status_code == 404
