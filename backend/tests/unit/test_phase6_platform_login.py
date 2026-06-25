"""Phase 6 平台登录 unit tests.

覆盖范围（per V1 task）：
- Bilib QR 生成 URL 格式（mocked httpx）
- storage_state save / load / clear
- Bilib poll 状态机：code 0 (success) / 86038 (expired) / 86090 (scanned) / 86039 (waiting)
- Bilib check_login_status（mocked nav API）
- LoginManager 平台分发 + 不支持平台报错
- Ixigua Playwright tests: 标记为 requires_playwright，默认 skip
"""
from __future__ import annotations

import base64
import io
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── LoginManager: storage_state save/load/clear ──

@pytest.fixture
def tmp_login_manager(tmp_path):
    from app.services.platform.manager import LoginManager
    return LoginManager(data_dir=str(tmp_path))


def test_manager_storage_state_path_single_account(tmp_login_manager):
    """单账号：{platform}_storage_state.json"""
    p = tmp_login_manager.storage_state_path("bilibili")
    assert p.endswith("bilibili_storage_state.json")


def test_manager_storage_state_path_multi_account(tmp_login_manager):
    """多账号接口预留：{platform}_{account_id}_storage_state.json"""
    p = tmp_login_manager.storage_state_path("ixigua", account_id="acc1")
    assert p.endswith("ixigua_acc1_storage_state.json")


def test_manager_save_load_storage_state(tmp_login_manager):
    """save → load 应能读回原数据."""
    state = {
        "platform": "bilibili",
        "saved_at": 1234567890,
        "cookies": {"SESSDATA": "abc", "bili_jie": "xyz"},
        "user_info": {"uid": 42, "username": "tester"},
    }
    path = tmp_login_manager.save_storage_state("bilibili", state)
    assert os.path.exists(path)

    loaded = tmp_login_manager.load_storage_state("bilibili")
    assert loaded is not None
    assert loaded["cookies"]["SESSDATA"] == "abc"
    assert loaded["user_info"]["username"] == "tester"


def test_manager_load_nonexistent_returns_none(tmp_login_manager):
    assert tmp_login_manager.load_storage_state("nonexistent") is None


def test_manager_clear_storage_state(tmp_login_manager):
    """save → clear → load 应为 None."""
    tmp_login_manager.save_storage_state("bilibili", {"cookies": {"x": "1"}})
    assert tmp_login_manager.clear_storage_state("bilibili") is True
    assert tmp_login_manager.load_storage_state("bilibili") is None


def test_manager_clear_nonexistent_returns_false(tmp_login_manager):
    assert tmp_login_manager.clear_storage_state("never_saved") is False


def test_manager_unsupported_platform_raises(tmp_login_manager):
    with pytest.raises(ValueError, match="Unsupported platform"):
        tmp_login_manager.get("youtube")


def test_manager_supported_platforms():
    from app.services.platform.manager import LoginManager
    assert set(LoginManager.SUPPORTED_PLATFORMS) == {"ixigua", "bilibili"}


def test_manager_get_bilibili_returns_instance(tmp_login_manager):
    from app.services.platform.bilibili import BilibiliLogin
    inst = tmp_login_manager.get("bilibili")
    assert isinstance(inst, BilibiliLogin)


def test_manager_get_caches_instance(tmp_login_manager):
    """多次 get 同一平台应返回同一实例."""
    a = tmp_login_manager.get("bilibili")
    b = tmp_login_manager.get("bilibili")
    assert a is b


# ── Bilib QR encoding ──

def test_bilibili_encode_qr_png_returns_valid_png():
    from app.services.platform.bilibili import BilibiliLogin
    b = BilibiliLogin(storage_state_path="/tmp/_test_bili.json")
    png = b._encode_qr_png("https://passport.bilibili.com/x/passport-login/web/qrcode?...fake")
    assert isinstance(png, bytes)
    # PNG magic bytes
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 100  # non-trivial


# ── Bilib QR start_qr_login (mocked httpx) ──

@pytest.mark.asyncio
async def test_bilibili_start_qr_login_extracts_qrcode_key(tmp_path):
    """Mocked httpx → start_qr_login 应返回 PNG bytes 并缓存 qrcode_key."""
    from app.services.platform.bilibili import BilibiliLogin

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "code": 0,
        "data": {
            "url": "https://passport.bilibili.com/h5-app/passport/login/scan?navhide=1&qrcode_key=abc123&from=SPC-QR-CODE",
            "qrcode_key": "abc123",
            "web_name": "哔哩哔哩",
        },
    }

    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=fake_response)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.platform.bilibili.httpx.AsyncClient", return_value=fake_client):
        login = BilibiliLogin(storage_state_path=str(tmp_path / "bili.json"))
        png = await login.start_qr_login()

    assert isinstance(png, bytes)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert login._qrcode_key == "abc123"


@pytest.mark.asyncio
async def test_bilibili_start_qr_login_raises_on_error_code(tmp_path):
    from app.services.platform.bilibili import BilibiliLogin

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {"code": -101, "message": "invalid"}

    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=fake_response)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.platform.bilibili.httpx.AsyncClient", return_value=fake_client):
        login = BilibiliLogin(storage_state_path=str(tmp_path / "bili.json"))
        with pytest.raises(RuntimeError, match="generate failed"):
            await login.start_qr_login()


# ── Bilib poll state machine ──

@pytest.mark.asyncio
async def test_bilibili_poll_waiting(tmp_path):
    """code=86039 → waiting."""
    from app.services.platform.bilibili import BilibiliLogin
    from app.services.platform.base import LoginStatus

    login = BilibiliLogin(storage_state_path=str(tmp_path / "bili.json"))
    login._qrcode_key = "fake_key"
    login._mark_session_start()

    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {
        "code": 0,
        "data": {"code": 86039, "message": "未扫码"},
    }
    fake_resp.cookies = {}

    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=fake_resp)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    # _fetch_nav 不应被调用（waiting 分支）
    fake_client.cookies = MagicMock()
    fake_client.cookies.jar = []

    with patch("app.services.platform.bilibili.httpx.AsyncClient", return_value=fake_client):
        result = await login.poll_login_status()

    assert result["status"] == LoginStatus.WAITING
    assert result["code"] == 86039


@pytest.mark.asyncio
async def test_bilibili_poll_scanned(tmp_path):
    """code=86090 → scanned."""
    from app.services.platform.bilibili import BilibiliLogin
    from app.services.platform.base import LoginStatus

    login = BilibiliLogin(storage_state_path=str(tmp_path / "bili.json"))
    login._qrcode_key = "fake_key"
    login._mark_session_start()

    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {
        "code": 0,
        "data": {"code": 86090, "message": "已扫码，等待确认"},
    }
    fake_resp.cookies = {}

    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=fake_resp)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.cookies = MagicMock()
    fake_client.cookies.jar = []

    with patch("app.services.platform.bilibili.httpx.AsyncClient", return_value=fake_client):
        result = await login.poll_login_status()

    assert result["status"] == LoginStatus.SCANNED


@pytest.mark.asyncio
async def test_bilibili_poll_expired(tmp_path):
    """code=86038 → expired."""
    from app.services.platform.bilibili import BilibiliLogin
    from app.services.platform.base import LoginStatus

    login = BilibiliLogin(storage_state_path=str(tmp_path / "bili.json"))
    login._qrcode_key = "fake_key"
    login._mark_session_start()

    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {
        "code": 0,
        "data": {"code": 86038, "message": "二维码已失效"},
    }
    fake_resp.cookies = {}

    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=fake_resp)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.cookies = MagicMock()
    fake_client.cookies.jar = []

    with patch("app.services.platform.bilibili.httpx.AsyncClient", return_value=fake_client):
        result = await login.poll_login_status()

    assert result["status"] == LoginStatus.EXPIRED


@pytest.mark.asyncio
async def test_bilibili_poll_success_persists_state(tmp_path):
    """code=0 → success, 持久化 storage_state, 返回 user_info."""
    from app.services.platform.bilibili import BilibiliLogin
    from app.services.platform.base import LoginStatus

    state_path = str(tmp_path / "bili.json")
    login = BilibiliLogin(storage_state_path=state_path)
    login._qrcode_key = "fake_key"
    login._mark_session_start()

    # poll response
    poll_resp = MagicMock()
    poll_resp.raise_for_status = MagicMock()
    poll_resp.json.return_value = {
        "code": 0,
        "data": {"code": 0, "message": "OK", "refresh_token": "rt"},
    }
    poll_resp.cookies = {"SESSDATA": "sess_data_val", "bili_jie": "jie_val"}

    # nav response (for user_info fetch)
    nav_resp = MagicMock()
    nav_resp.raise_for_status = MagicMock()
    nav_resp.json.return_value = {
        "code": 0,
        "data": {
            "isLogin": True,
            "mid": 12345,
            "uname": "test_user",
            "face": "https://example.com/avatar.png",
            "vipType": 1,
            "level_info": {"current_level": 6},
        },
    }

    fake_client = AsyncMock()
    fake_client.get = AsyncMock(side_effect=[poll_resp, nav_resp])
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.cookies = MagicMock()
    fake_client.cookies.jar = []

    with patch("app.services.platform.bilibili.httpx.AsyncClient", return_value=fake_client):
        result = await login.poll_login_status()

    assert result["status"] == LoginStatus.SUCCESS
    assert result["cookies"]["SESSDATA"] == "sess_data_val"
    assert result["user_info"]["isLogin"] is True
    assert result["user_info"]["uid"] == 12345
    assert result["user_info"]["username"] == "test_user"

    # storage_state persisted
    assert os.path.exists(state_path)
    with open(state_path, "r", encoding="utf-8") as f:
        persisted = json.load(f)
    assert persisted["cookies"]["SESSDATA"] == "sess_data_val"
    assert persisted["user_info"]["uid"] == 12345


@pytest.mark.asyncio
async def test_bilibili_poll_no_qrcode_key_returns_failed(tmp_path):
    """未启动 start_qr_login 直接 poll 应返回 failed."""
    from app.services.platform.bilibili import BilibiliLogin
    from app.services.platform.base import LoginStatus

    login = BilibiliLogin(storage_state_path=str(tmp_path / "bili.json"))
    result = await login.poll_login_status()
    assert result["status"] == LoginStatus.FAILED


# ── Bilib check_login_status ──

@pytest.mark.asyncio
async def test_bilibili_check_login_status_no_state_returns_false(tmp_path):
    from app.services.platform.bilibili import BilibiliLogin
    login = BilibiliLogin(storage_state_path=str(tmp_path / "missing.json"))
    assert await login.check_login_status() is False


@pytest.mark.asyncio
async def test_bilibili_check_login_status_logged_in(tmp_path):
    from app.services.platform.bilibili import BilibiliLogin

    state_path = tmp_path / "bili.json"
    state_path.write_text(json.dumps({
        "platform": "bilibili",
        "cookies": {"SESSDATA": "abc"},
        "user_info": {"uid": 1},
    }), encoding="utf-8")

    nav_resp = MagicMock()
    nav_resp.raise_for_status = MagicMock()
    nav_resp.json.return_value = {
        "code": 0,
        "data": {"isLogin": True, "mid": 1, "uname": "u"},
    }

    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=nav_resp)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.platform.bilibili.httpx.AsyncClient", return_value=fake_client):
        login = BilibiliLogin(storage_state_path=str(state_path))
        result = await login.check_login_status()

    assert result is True


# ── Bilib logout ──

@pytest.mark.asyncio
async def test_bilibili_logout_removes_state_file(tmp_path):
    from app.services.platform.bilibili import BilibiliLogin

    state_path = tmp_path / "bili.json"
    state_path.write_text(json.dumps({"cookies": {"x": "y"}}), encoding="utf-8")

    login = BilibiliLogin(storage_state_path=str(state_path))
    login._qrcode_key = "abc"
    await login.logout()

    assert not state_path.exists()
    assert login._qrcode_key is None


# ── Platform API endpoints (HTTP smoke) ──

def test_platform_state_endpoint_returns_both_platforms():
    """GET /api/platform/state 返回 ixigua + bilibili 两项."""
    from fastapi.testclient import TestClient

    # 用临时 data_dir，避免污染开发环境
    with tempfile.TemporaryDirectory() as tmp_data:
        # 重置 manager 单例
        import app.services.platform.manager as mgr_mod
        mgr_mod._manager = mgr_mod.LoginManager(data_dir=tmp_data)

        from app.main import app
        client = TestClient(app)
        resp = client.get("/api/platform/state")

    assert resp.status_code == 200
    body = resp.json()
    platforms = {p["platform"]: p for p in body["platforms"]}
    assert set(platforms.keys()) == {"ixigua", "bilibili", "douyin"}
    assert platforms["bilibili"]["display_name"] == "哔哩哔哩"
    assert platforms["ixigua"]["display_name"] == "西瓜视频"
    assert platforms["douyin"]["display_name"] == "抖音"
    # 无登录态 — bilibili/ixigua 使用 temp data dir，douyin 可能已经有本地 cookie
    assert platforms["bilibili"]["logged_in"] is False
    assert platforms["ixigua"]["logged_in"] is False


def test_platform_unknown_returns_404():
    """GET /api/platform/youtube/... 应返回 404."""
    import app.services.platform.manager as mgr_mod
    from fastapi.testclient import TestClient
    with tempfile.TemporaryDirectory() as tmp_data:
        mgr_mod._manager = mgr_mod.LoginManager(data_dir=tmp_data)
        from app.main import app
        client = TestClient(app)
        resp = client.get("/api/platform/youtube/login/status")
    assert resp.status_code == 404


def test_platform_status_no_state_returns_not_logged_in():
    """未登录状态下 GET /login/status 返回 not_logged_in."""
    import app.services.platform.manager as mgr_mod
    from fastapi.testclient import TestClient
    with tempfile.TemporaryDirectory() as tmp_data:
        mgr_mod._manager = mgr_mod.LoginManager(data_dir=tmp_data)
        from app.main import app
        client = TestClient(app)
        resp = client.get("/api/platform/bilibili/login/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "not_logged_in"


def test_platform_logout_no_state_still_succeeds():
    """无登录态登出也应返回 success=True."""
    import app.services.platform.manager as mgr_mod
    from fastapi.testclient import TestClient
    with tempfile.TemporaryDirectory() as tmp_data:
        mgr_mod._manager = mgr_mod.LoginManager(data_dir=tmp_data)
        from app.main import app
        client = TestClient(app)
        resp = client.post("/api/platform/bilibili/logout")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True


# ── Ixigua Playwright tests (skip by default) ──

@pytest.mark.requires_playwright
@pytest.mark.asyncio
async def test_ixigua_playwright_start_qr_login(tmp_path):
    """实际启动 Playwright — 默认 skip."""
    from app.services.platform.ixigua import IxiguaLogin
    login = IxiguaLogin(storage_state_path=str(tmp_path / "ixg.json"), headless=True)
    png = await login.start_qr_login()
    assert isinstance(png, bytes)
    await login.logout()


def test_ixigua_check_login_status_no_state(tmp_path):
    """无 storage_state → check_login_status=False (不需 Playwright)."""
    import asyncio
    from app.services.platform.ixigua import IxiguaLogin
    login = IxiguaLogin(storage_state_path=str(tmp_path / "missing.json"))
    result = asyncio.get_event_loop().run_until_complete(login.check_login_status())
    assert result is False


def test_ixigua_storage_state_load_save(tmp_path):
    """Ixigua 共用 manager 流程的子集 — 直接测 _load/_persist."""
    from app.services.platform.ixigua import IxiguaLogin
    state_path = tmp_path / "ixg.json"
    login = IxiguaLogin(storage_state_path=str(state_path))

    # 初始无文件
    assert login._load_storage_state() is None

    # 持久化
    login._persist_storage_state({
        "platform": "ixigua",
        "cookies": {"sessionid": "abc"},
        "user_info": {"uid": 99, "username": "xigua_user"},
    })
    assert state_path.exists()

    loaded = login._load_storage_state()
    assert loaded is not None
    assert loaded["cookies"]["sessionid"] == "abc"
    assert loaded["user_info"]["uid"] == 99
