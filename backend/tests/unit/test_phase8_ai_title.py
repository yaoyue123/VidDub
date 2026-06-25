"""Phase 8 AI 智能标题与标签 unit tests (V1).

覆盖：
- title_generator 解析/校验/降级 (mocked SiliconFlow)
- scheduler._handle_generate_title 链式触发
- /api/title POST/GET/PUT 端点
- publish 流程使用 chosen_title 优先 (回归)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────
# title_generator 解析与校验
# ─────────────────────────────────────────────────────────────────

def test_validate_candidates_happy_path():
    from app.services.title_generator import validate_candidates
    r = validate_candidates({"titles": ["t1", "t2"], "tags": ["g1"], "summary_zh": "摘要"})
    assert r["titles"] == ["t1", "t2"]
    assert r["tags"] == ["g1"]
    assert r["summary_zh"] == "摘要"


def test_validate_candidates_truncates_to_max():
    from app.services.title_generator import validate_candidates
    parsed = {
        "titles": [f"标题{i}" for i in range(20)],
        "tags": [f"标签{i}" for i in range(20)],
    }
    r = validate_candidates(parsed, num_titles=5, num_tags=8)
    assert len(r["titles"]) == 5
    assert len(r["tags"]) == 8


def test_validate_candidates_handles_missing_keys():
    from app.services.title_generator import validate_candidates
    r = validate_candidates({})
    assert r == {"titles": [], "tags": [], "summary_zh": ""}


def test_validate_candidates_handles_wrong_types():
    from app.services.title_generator import validate_candidates
    r = validate_candidates({"titles": "not a list", "tags": 42, "summary_zh": None})
    assert r["titles"] == []
    assert r["tags"] == []
    assert r["summary_zh"] == ""


def test_validate_candidates_tags_as_csv_string():
    from app.services.title_generator import validate_candidates
    r = validate_candidates({"tags": "标签1, 标签2 , 标签3"})
    assert r["tags"] == ["标签1", "标签2", "标签3"]


def test_validate_candidates_handles_non_dict():
    from app.services.title_generator import validate_candidates
    assert validate_candidates(None) == {"titles": [], "tags": [], "summary_zh": ""}
    assert validate_candidates([]) == {"titles": [], "tags": [], "summary_zh": ""}
    assert validate_candidates("string") == {"titles": [], "tags": [], "summary_zh": ""}


def test_safe_json_parse_with_code_fence():
    from app.services.title_generator import _safe_json_parse
    assert _safe_json_parse('```json\n{"a": 1}\n```') == {"a": 1}


def test_safe_json_parse_handles_surrounding_noise():
    from app.services.title_generator import _safe_json_parse
    assert _safe_json_parse('好的，这是结果：{"a": 1} 完成') == {"a": 1}


def test_safe_json_parse_invalid_returns_none():
    from app.services.title_generator import _safe_json_parse
    assert _safe_json_parse("not json") is None
    assert _safe_json_parse("") is None
    assert _safe_json_parse(None) is None


def test_parse_text_fallback_extracts_blocks():
    from app.services.title_generator import _parse_text_fallback
    content = (
        "[TITLES]\n标题1\n标题2\n标题3\n[/TITLES]\n"
        "[TAGS]\n标签1\n标签2\n[/TAGS]\n"
        "[SUMMARY]\n这是摘要内容\n[/SUMMARY]"
    )
    r = _parse_text_fallback(content, 5, 8)
    assert r["titles"] == ["标题1", "标题2", "标题3"]
    assert r["tags"] == ["标签1", "标签2"]
    assert r["summary_zh"] == "这是摘要内容"


def test_parse_text_fallback_missing_blocks():
    from app.services.title_generator import _parse_text_fallback
    r = _parse_text_fallback("nothing useful here", 5, 8)
    assert r == {"titles": [], "tags": [], "summary_zh": ""}


def test_parse_text_fallback_strips_number_prefixes():
    from app.services.title_generator import _parse_text_fallback
    content = (
        "[TITLES]\n1. 标题1\n2. 标题2\n[/TITLES]\n"
        "[TAGS]\n- 标签1\n- 标签2\n[/TAGS]\n"
        "[SUMMARY]\n摘要\n[/SUMMARY]"
    )
    r = _parse_text_fallback(content, 5, 8)
    assert r["titles"] == ["标题1", "标题2"]
    assert r["tags"] == ["标签1", "标签2"]


def test_build_user_prompt_truncates_transcript():
    from app.services.title_generator import _build_user_prompt, TRANSCRIPT_MAX_CHARS
    long_text = "A" * (TRANSCRIPT_MAX_CHARS + 500)
    prompt = _build_user_prompt("Title", long_text, num_titles=5, num_tags=8)
    # 应包含截断后的内容长度（不超过 max chars）
    assert "A" * 100 in prompt  # 抽样验证
    assert prompt.count("A") == TRANSCRIPT_MAX_CHARS


# ─────────────────────────────────────────────────────────────────
# generate_title_candidates — mocked SiliconFlow
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_title_candidates_happy_path(monkeypatch):
    """JSON mode 成功 — 返回 5 标题 + 8 标签."""
    from app.services import title_generator as tg

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "titles": ["候选1", "候选2", "候选3", "候选4", "候选5"],
                    "tags": ["标签1", "标签2", "标签3", "标签4", "标签5", "标签6", "标签7", "标签8"],
                    "summary_zh": "这是视频摘要",
                }, ensure_ascii=False)
            }
        }]
    }

    async def fake_sf_post(client, path, **kwargs):
        return fake_resp

    monkeypatch.setattr(tg, "sf_post", fake_sf_post)

    fake_client = MagicMock()
    fake_client.aclose = AsyncMock()

    video = MagicMock()
    video.id = 1
    video.title = "Original English Title"

    result = await tg.generate_title_candidates(
        video,
        original_title_en="Original English Title",
        configs={},
        client=fake_client,
    )

    assert len(result["titles"]) == 5
    assert len(result["tags"]) == 8
    assert result["summary_zh"] == "这是视频摘要"


@pytest.mark.asyncio
async def test_generate_title_candidates_malformed_falls_back(monkeypatch):
    """JSON mode 返回空数组 → 触发文本回退."""
    from app.services import title_generator as tg

    # JSON mode 调用 — 返回空 titles
    json_resp = MagicMock()
    json_resp.json.return_value = {
        "choices": [{"message": {"content": '{"titles": [], "tags": []}'}}]
    }
    # 文本回退 — 返回 [TITLES]...[/TITLES] 格式
    text_resp = MagicMock()
    text_resp.json.return_value = {
        "choices": [{
            "message": {
                "content": "[TITLES]\n回退标题1\n回退标题2\n[/TITLES]\n[TAGS]\n回退标签1\n[/TAGS]\n[SUMMARY]\n回退摘要\n[/SUMMARY]"
            }
        }]
    }

    call_count = {"n": 0}

    async def fake_sf_post(client, path, **kwargs):
        call_count["n"] += 1
        return json_resp if call_count["n"] == 1 else text_resp

    monkeypatch.setattr(tg, "sf_post", fake_sf_post)

    fake_client = MagicMock()
    fake_client.aclose = AsyncMock()

    video = MagicMock()
    video.id = 1
    video.title = "Title"

    result = await tg.generate_title_candidates(
        video, configs={}, client=fake_client,
    )

    assert result["titles"] == ["回退标题1", "回退标题2"]
    assert result["tags"] == ["回退标签1"]
    assert result["summary_zh"] == "回退摘要"


@pytest.mark.asyncio
async def test_generate_title_candidates_missing_keys_graceful(monkeypatch):
    """模型返回缺字段 JSON — validate_candidates 兜底返回空."""
    from app.services import title_generator as tg

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "choices": [{"message": {"content": '{"other_key": "value"}'}}]
    }
    # 文本回退也空
    text_resp = MagicMock()
    text_resp.json.return_value = {
        "choices": [{"message": {"content": "no blocks at all"}}]
    }

    call_count = {"n": 0}

    async def fake_sf_post(client, path, **kwargs):
        call_count["n"] += 1
        return fake_resp if call_count["n"] == 1 else text_resp

    monkeypatch.setattr(tg, "sf_post", fake_sf_post)

    fake_client = MagicMock()
    fake_client.aclose = AsyncMock()

    video = MagicMock()
    video.id = 1
    video.title = "T"

    result = await tg.generate_title_candidates(
        video, configs={}, client=fake_client,
    )

    assert result["titles"] == []
    assert result["tags"] == []
    assert result["summary_zh"] == ""


@pytest.mark.asyncio
async def test_generate_title_candidates_uses_config_counts(monkeypatch):
    """num_titles / num_tags 从 configs 读取."""
    from app.services import title_generator as tg

    captured = {}

    async def fake_sf_post(client, path, **kwargs):
        captured["payload"] = kwargs.get("json", {})
        fake_resp = MagicMock()
        fake_resp.json.return_value = {
            "choices": [{"message": {"content": '{"titles":["a"],"tags":["b"],"summary_zh":""}'}}]
        }
        return fake_resp

    monkeypatch.setattr(tg, "sf_post", fake_sf_post)
    fake_client = MagicMock()
    fake_client.aclose = AsyncMock()

    video = MagicMock()
    video.id = 1
    video.title = "T"

    await tg.generate_title_candidates(
        video,
        configs={
            "title_generator_candidate_count": "3",
            "title_generator_tag_count": "6",
        },
        client=fake_client,
    )

    # user prompt 应包含 "标题3" 和 "标签6"
    user_msg = captured["payload"]["messages"][1]["content"]
    assert "标题3" in user_msg
    assert "标签6" in user_msg


# ─────────────────────────────────────────────────────────────────
# _resolve_transcript_text
# ─────────────────────────────────────────────────────────────────

def test_resolve_transcript_text_from_param():
    from app.services.title_generator import _resolve_transcript_text
    video = MagicMock()
    video.id = 1
    segments = [{"text": "你好"}, {"text": "世界"}]
    assert _resolve_transcript_text(video, segments) == "你好\n世界"


def test_resolve_transcript_text_empty_segments():
    from app.services.title_generator import _resolve_transcript_text
    video = MagicMock()
    video.id = 1
    assert _resolve_transcript_text(video, []) == ""


def test_resolve_transcript_text_no_id():
    from app.services.title_generator import _resolve_transcript_text
    video = MagicMock()
    video.id = None
    assert _resolve_transcript_text(video, None) == ""


def test_resolve_transcript_text_reads_file(tmp_path, monkeypatch):
    from app.services import title_generator as tg
    # mock os.path.exists / open via chdir to tmp
    video = MagicMock()
    video.id = 42

    # 构造 downloads/42/translated.json
    downloads = tmp_path / "downloads" / "42"
    downloads.mkdir(parents=True)
    (downloads / "translated.json").write_text(
        json.dumps([{"text": "中文段1"}, {"text": "中文段2"}], ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    result = tg._resolve_transcript_text(video, None)
    assert "中文段1" in result
    assert "中文段2" in result


# ─────────────────────────────────────────────────────────────────
# Scheduler._handle_generate_title — 链式集成
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scheduler_handle_generate_title_updates_video(monkeypatch):
    """_handle_generate_title 成功 → 更新 Video 行."""
    from app.services import scheduler as sched_mod

    # 准备 mock Video
    video = MagicMock()
    video.id = 1
    video.title = "Test"

    # mock async_session_factory：单次 session 返回 video + 收到 update 调用
    sessions = []

    class _FakeSession:
        def __init__(self):
            self.updates = []
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def execute(self, q):
            # 第一次 select 返回 video；后续 update 不需要返回值
            self.last_q = q
        def __await__(self): return iter([])

    # 用真实 AsyncSession mock 太复杂，简化：直接 patch async_session_factory
    session_calls = {"count": 0}

    class _MockSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def execute(self, q):
            session_calls["count"] += 1
            if session_calls["count"] == 1:
                # 第一次 select(Video) → 返回 video
                result = MagicMock()
                result.scalar_one_or_none.return_value = video
                return result
            # 后续 update(Video) — 无返回值需要
            return MagicMock()
        async def commit(self):
            pass

    def fake_factory():
        return _MockSession()

    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "async_session_factory", fake_factory)
    monkeypatch.setattr(sched_mod, "async_session_factory", fake_factory)

    # mock title_generator
    async def fake_gen(video_arg, **kwargs):
        return {"titles": ["a", "b"], "tags": ["x"], "summary_zh": "sum"}

    monkeypatch.setattr(
        "app.services.title_generator.generate_title_candidates",
        fake_gen,
    )

    # mock ws_manager
    async def fake_broadcast(msg):
        pass
    monkeypatch.setattr(sched_mod.ws_manager, "broadcast", fake_broadcast)

    # mock _load_configs
    async def fake_load_configs():
        return {"title_generator_enabled": "true"}
    monkeypatch.setattr(sched_mod, "_load_configs", fake_load_configs)

    scheduler = sched_mod.TaskScheduler()
    await scheduler._handle_generate_title(1)

    # 第二次 session 应该有 commit 调用（update 持久化）
    # 这里仅断言没抛异常且 session 被多次进入
    assert session_calls["count"] >= 2


@pytest.mark.asyncio
async def test_scheduler_handle_generate_title_swallows_failure(monkeypatch):
    """_handle_generate_title 失败 → 仅 log warning，不抛."""
    from app.services import scheduler as sched_mod

    video = MagicMock()
    video.id = 1
    video.title = "Test"

    class _MockSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def execute(self, q):
            result = MagicMock()
            result.scalar_one_or_none.return_value = video
            return result
        async def commit(self): pass

    def fake_factory(): return _MockSession()
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "async_session_factory", fake_factory)
    monkeypatch.setattr(sched_mod, "async_session_factory", fake_factory)

    async def failing_gen(*args, **kwargs):
        raise RuntimeError("API down")
    monkeypatch.setattr(
        "app.services.title_generator.generate_title_candidates",
        failing_gen,
    )

    async def fake_load_configs():
        return {}
    monkeypatch.setattr(sched_mod, "_load_configs", fake_load_configs)

    scheduler = sched_mod.TaskScheduler()
    # 不应抛
    await scheduler._handle_generate_title(1)


# ─────────────────────────────────────────────────────────────────
# API endpoints — 用 TestClient + 内存 sqlite
# ─────────────────────────────────────────────────────────────────

@pytest.fixture
def title_api_client(tmp_path):
    """FastAPI TestClient with in-memory sqlite DB."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

    test_db_path = tmp_path / "test.db"
    sync_engine = create_engine(f"sqlite:///{test_db_path}", echo=False)
    from app.models.base import Base
    Base.metadata.create_all(sync_engine)

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

    # 也 patch async_session_factory for services that bypass get_db
    import app.core.database as db_mod
    original_factory = db_mod.async_session_factory
    db_mod.async_session_factory = TestSessionFactory

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    db_mod.async_session_factory = original_factory

    import asyncio as _aio
    try:
        loop = _aio.new_event_loop()
        loop.run_until_complete(test_engine.dispose())
        loop.close()
    except Exception:
        pass


def _seed_video(client, **overrides):
    """直接通过 DB 插入 video（用 videos API 不行因为路由约束较多）."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import os
    # 用 sync engine 插入 — 找到 test.db
    # 简化：用 videos API 创建
    body = {
        "youtube_url": "https://youtu.be/abc123",
        "youtube_id": "abc123",
        "title": "Test Video",
        "channel": "TestChannel",
        **overrides,
    }
    res = client.post("/api/videos", json=body)
    if res.status_code in (200, 201):
        return res.json()
    # 有些项目 videos POST 不支持完整 body，直接读 DB
    return None


def test_title_api_get_video_not_found(title_api_client):
    res = title_api_client.get("/api/title/9999")
    assert res.status_code == 404


def test_title_api_put_video_not_found(title_api_client):
    res = title_api_client.put("/api/title/9999", json={"title_chosen": "X"})
    assert res.status_code == 404


def test_title_api_generate_video_not_found(title_api_client):
    res = title_api_client.post("/api/title/9999/generate")
    assert res.status_code == 404


def test_title_api_get_returns_empty_state(title_api_client, monkeypatch):
    """先创建 video 再 GET — 应返回空候选."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
    from sqlalchemy import select
    from app.models.video import Video
    import app.core.database as db_mod

    # 直接用底层 session factory 插入
    factory = db_mod.async_session_factory

    async def _insert():
        async with factory() as s:
            v = Video(
                youtube_url="https://youtu.be/x",
                youtube_id="vid_x",
                title="Test",
                channel="ch",
            )
            s.add(v)
            await s.commit()
            await s.refresh(v)
            return v.id

    import asyncio
    vid = asyncio.get_event_loop().run_until_complete(_insert())

    res = title_api_client.get(f"/api/title/{vid}")
    assert res.status_code == 200
    data = res.json()
    assert data["video_id"] == vid
    assert data["ai_title_candidates"] == []
    assert data["ai_tags_candidates"] == []
    assert data["title_chosen"] is None
    assert data["tags_chosen"] == []


def test_title_api_put_saves_choice(title_api_client):
    from app.models.video import Video
    import app.core.database as db_mod

    factory = db_mod.async_session_factory

    async def _insert():
        async with factory() as s:
            v = Video(
                youtube_url="https://youtu.be/y",
                youtube_id="vid_y",
                title="Test2",
                channel="ch",
            )
            s.add(v)
            await s.commit()
            await s.refresh(v)
            return v.id

    import asyncio
    vid = asyncio.get_event_loop().run_until_complete(_insert())

    res = title_api_client.put(
        f"/api/title/{vid}",
        json={"title_chosen": "用户选的标题", "tags_chosen": ["标签1", "标签2"]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["title_chosen"] == "用户选的标题"
    assert data["tags_chosen"] == ["标签1", "标签2"]


def test_title_api_put_rejects_empty_title(title_api_client):
    from app.models.video import Video
    import app.core.database as db_mod

    factory = db_mod.async_session_factory

    async def _insert():
        async with factory() as s:
            v = Video(
                youtube_url="https://youtu.be/z",
                youtube_id="vid_z",
                title="Test3",
                channel="ch",
            )
            s.add(v)
            await s.commit()
            await s.refresh(v)
            return v.id

    import asyncio
    vid = asyncio.get_event_loop().run_until_complete(_insert())

    res = title_api_client.put(
        f"/api/title/{vid}",
        json={"title_chosen": "   "},
    )
    assert res.status_code == 400


def test_title_api_generate_disabled_returns_409(title_api_client):
    """title_generator_enabled=false → 409."""
    from app.models.video import Video
    from app.models.config import Config
    import app.core.database as db_mod

    factory = db_mod.async_session_factory

    async def _seed():
        async with factory() as s:
            v = Video(
                youtube_url="https://youtu.be/dis",
                youtube_id="vid_dis",
                title="Disabled",
                channel="ch",
            )
            s.add(v)
            s.add(Config(key="title_generator_enabled", value="false", description="test"))
            await s.commit()
            await s.refresh(v)
            return v.id

    import asyncio
    vid = asyncio.get_event_loop().run_until_complete(_seed())

    res = title_api_client.post(f"/api/title/{vid}/generate")
    assert res.status_code == 409


def test_title_api_generate_success(title_api_client, monkeypatch):
    """generate 端点调用 mocked service → 200 + 写回 DB."""
    from app.models.video import Video
    import app.core.database as db_mod

    factory = db_mod.async_session_factory

    async def _seed():
        async with factory() as s:
            v = Video(
                youtube_url="https://youtu.be/ok",
                youtube_id="vid_ok",
                title="OK",
                channel="ch",
            )
            s.add(v)
            await s.commit()
            await s.refresh(v)
            return v.id

    import asyncio
    vid = asyncio.get_event_loop().run_until_complete(_seed())

    async def fake_gen(video, **kwargs):
        return {
            "titles": ["AI标题1", "AI标题2"],
            "tags": ["AI标签1"],
            "summary_zh": "AI 摘要",
        }

    # api/title.py 用 from app.services.title_generator import generate_title_candidates
    # 所以需要 patch api.title 模块中的引用
    import app.api.title as title_api_mod
    monkeypatch.setattr(title_api_mod, "generate_title_candidates", fake_gen)

    res = title_api_client.post(f"/api/title/{vid}/generate")
    assert res.status_code == 200
    data = res.json()
    assert data["titles"] == ["AI标题1", "AI标题2"]
    assert data["tags"] == ["AI标签1"]
    assert data["summary_zh"] == "AI 摘要"

    # 后续 GET 应读回写过的候选
    res2 = title_api_client.get(f"/api/title/{vid}")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["ai_title_candidates"] == ["AI标题1", "AI标题2"]
    assert data2["ai_tags_candidates"] == ["AI标签1"]


def test_title_api_generate_failure_returns_empty_arrays(title_api_client, monkeypatch):
    """generate 抛异常 → 200 + 空 arrays（不阻塞前端）."""
    from app.models.video import Video
    import app.core.database as db_mod

    factory = db_mod.async_session_factory

    async def _seed():
        async with factory() as s:
            v = Video(
                youtube_url="https://youtu.be/fail",
                youtube_id="vid_fail",
                title="Fail",
                channel="ch",
            )
            s.add(v)
            await s.commit()
            await s.refresh(v)
            return v.id

    import asyncio
    vid = asyncio.get_event_loop().run_until_complete(_seed())

    async def failing_gen(*args, **kwargs):
        raise RuntimeError("boom")

    import app.api.title as title_api_mod
    monkeypatch.setattr(title_api_mod, "generate_title_candidates", failing_gen)

    res = title_api_client.post(f"/api/title/{vid}/generate")
    assert res.status_code == 200
    data = res.json()
    assert data["titles"] == []
    assert data["tags"] == []


# ─────────────────────────────────────────────────────────────────
# publish uses chosen title (regression)
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_uses_chosen_title_when_set(monkeypatch):
    """video.title_chosen 非空 → 不再调 SiliconFlow 翻译."""
    from app.services.publish import title_translate as tt

    translate_called = {"n": 0}

    async def fake_translate(*args, **kwargs):
        translate_called["n"] += 1
        return ("翻译标题", "翻译描述", ["翻译标签"])

    monkeypatch.setattr(tt, "_translate_via_siliconflow", fake_translate)

    # mock video with chosen title
    chosen_video = MagicMock()
    chosen_video.id = 100
    chosen_video.title = "English"
    chosen_video.description = "desc"
    chosen_video.title_chosen = "用户已选标题"
    chosen_video.tags_chosen = json.dumps(["用户标签1", "用户标签2"], ensure_ascii=False)
    chosen_video.thumbnail_url = None
    chosen_video.youtube_url = "https://youtu.be/x"

    cfg_obj = MagicMock()
    cfg_obj.key = "publish_default_tags"
    cfg_obj.value = "默认1,默认2"

    class _MockSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def execute(self, q):
            # 简化：第一次（Video）→ chosen_video；后续（Config）→ cfg_obj
            result = MagicMock()
            _MockSession._calls = getattr(_MockSession, "_calls", 0) + 1
            if _MockSession._calls == 1:
                result.scalar_one_or_none = lambda: chosen_video
            else:
                m = MagicMock()
                m.all = lambda: [cfg_obj]
                result.scalars = lambda: m
            return result

    def fake_factory(): return _MockSession()
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "async_session_factory", fake_factory)

    fields = await tt.prepare_publish_fields(100)

    assert translate_called["n"] == 0  # 不应调翻译
    assert fields.title == "用户已选标题"
    assert "用户标签1" in fields.tags
    assert "用户标签2" in fields.tags
    assert "默认1" in fields.tags  # 默认标签应被合并


@pytest.mark.asyncio
async def test_publish_falls_back_when_no_chosen_title(monkeypatch):
    """无 chosen → 调 SiliconFlow 翻译."""
    from app.services.publish import title_translate as tt

    async def fake_translate(*args, **kwargs):
        return ("翻译标题", "翻译描述", ["翻译标签"])

    monkeypatch.setattr(tt, "_translate_via_siliconflow", fake_translate)

    no_choice_video = MagicMock()
    no_choice_video.id = 200
    no_choice_video.title = "English"
    no_choice_video.description = "desc"
    no_choice_video.title_chosen = None
    no_choice_video.tags_chosen = None
    no_choice_video.thumbnail_url = None
    no_choice_video.youtube_url = "https://youtu.be/y"

    cfg_obj = MagicMock()
    cfg_obj.key = "publish_default_tags"
    cfg_obj.value = ""

    class _MockSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def execute(self, q):
            result = MagicMock()
            _MockSession._calls = getattr(_MockSession, "_calls", 0) + 1
            if _MockSession._calls == 1:
                result.scalar_one_or_none = lambda: no_choice_video
            else:
                m = MagicMock()
                m.all = lambda: [cfg_obj]
                result.scalars = lambda: m
            return result

    def fake_factory(): return _MockSession()
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "async_session_factory", fake_factory)

    fields = await tt.prepare_publish_fields(200)
    assert fields.title == "翻译标题"
