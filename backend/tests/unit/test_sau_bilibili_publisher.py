"""Tests for SAU-based Bilibili publisher (sau_bilibili.py) and cookie bridge.

Covers:
- cookie_bridge: conversion from storage_state to biliup LoginInfo format
- SauBilibiliPublisher: validate_login, publish (mocked subprocess)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────
# Cookie bridge tests
# ─────────────────────────────────────────────────────────────────

@pytest.fixture
def storage_state_dict_format() -> dict:
    """Phase 6 dict format: {cookies: {name: value}, user_info: {...}}"""
    return {
        "cookies": {
            "SESSDATA": "abc123",
            "bili_jct": "xyz789",
            "DedeUserID": "12345",
            "buvid3": "test-buvid3",
            "sid": "testsid",
        },
        "user_info": {"uid": 12345, "username": "tester"},
    }


@pytest.fixture
def storage_state_list_format() -> dict:
    """Playwright standard format: {cookies: [{name, value, domain, path}, ...]}"""
    return {
        "cookies": [
            {"name": "SESSDATA", "value": "abc123", "domain": ".bilibili.com", "path": "/"},
            {"name": "bili_jct", "value": "xyz789", "domain": ".bilibili.com", "path": "/"},
            {"name": "DedeUserID", "value": "12345", "domain": ".bilibili.com", "path": "/"},
            {"name": "buvid3", "value": "test-buvid3", "domain": ".bilibili.com", "path": "/"},
        ],
        "user_info": {"uid": 12345, "username": "tester"},
    }


def test_cookie_bridge_dict_format(storage_state_dict_format, tmp_path):
    from app.services.publish.cookie_bridge import convert_storage_state_to_biliup
    out = tmp_path / "biliup_cookies.json"
    result = convert_storage_state_to_biliup(storage_state_dict_format, str(out))
    assert result == str(out)
    assert out.exists()

    data = json.loads(out.read_text(encoding="utf-8"))
    assert "cookie_info" in data
    assert "sso" in data
    assert data["sso"] == []
    assert "token_info" in data

    assert data["cookie_info"]["SESSDATA"] == "abc123"
    assert data["cookie_info"]["bili_jct"] == "xyz789"
    assert data["cookie_info"]["DedeUserID"] == "12345"
    assert data["token_info"]["mid"] == 12345


def test_cookie_bridge_list_format(storage_state_list_format, tmp_path):
    from app.services.publish.cookie_bridge import convert_storage_state_to_biliup
    out = tmp_path / "biliup_cookies.json"
    result = convert_storage_state_to_biliup(storage_state_list_format, str(out))
    assert out.exists()

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["cookie_info"]["SESSDATA"] == "abc123"
    assert data["cookie_info"]["DedeUserID"] == "12345"


def test_cookie_bridge_missing_sessdata(tmp_path):
    from app.services.publish.cookie_bridge import convert_storage_state_to_biliup
    bad_state = {"cookies": {"bili_jct": "xyz"}, "user_info": {}}
    out = tmp_path / "bad.json"
    with pytest.raises(ValueError, match="SESSDATA"):
        convert_storage_state_to_biliup(bad_state, str(out))


def test_cookie_bridge_missing_bili_jct(tmp_path):
    from app.services.publish.cookie_bridge import convert_storage_state_to_biliup
    bad_state = {"cookies": {"SESSDATA": "abc"}, "user_info": {}}
    out = tmp_path / "bad.json"
    with pytest.raises(ValueError, match="bili_jct"):
        convert_storage_state_to_biliup(bad_state, str(out))


def test_cookie_bridge_empty_cookies(tmp_path):
    from app.services.publish.cookie_bridge import convert_storage_state_to_biliup
    bad_state = {"cookies": {}, "user_info": {}}
    out = tmp_path / "bad.json"
    with pytest.raises(ValueError, match="SESSDATA"):
        convert_storage_state_to_biliup(bad_state, str(out))


def test_cookie_bridge_weird_cookie_types(tmp_path):
    """Edge case: cookies is neither dict nor list (should not crash)."""
    from app.services.publish.cookie_bridge import convert_storage_state_to_biliup
    bad_state = {"cookies": "string", "user_info": {}}
    out = tmp_path / "weird.json"
    with pytest.raises(ValueError, match="SESSDATA"):
        convert_storage_state_to_biliup(bad_state, str(out))


def test_create_temp_cookie_file(storage_state_dict_format):
    from app.services.publish.cookie_bridge import create_temp_cookie_file
    path = create_temp_cookie_file(storage_state_dict_format)
    try:
        assert os.path.exists(path)
        assert path.endswith(".json")
        data = json.loads(open(path, encoding="utf-8").read())
        assert data["cookie_info"]["SESSDATA"] == "abc123"
    finally:
        os.unlink(path)


# ─────────────────────────────────────────────────────────────────
# SauBilibiliPublisher tests
# ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sau_bili_state_file(tmp_path):
    """Storage state file for SauBilibiliPublisher tests."""
    state = {
        "cookies": {"SESSDATA": "abc", "bili_jct": "xyz", "DedeUserID": "42"},
        "user_info": {"uid": 42, "username": "tester"},
    }
    p = tmp_path / "bilibili_storage_state.json"
    p.write_text(json.dumps(state), encoding="utf-8")
    return str(p)


@pytest.mark.asyncio
async def test_sau_validate_login_uses_biliup_renew(sau_bili_state_file):
    """validate_login should call `python -m biliup -u <cookie> renew`."""
    from app.services.publish.sau_bilibili import SauBilibiliPublisher

    pub = SauBilibiliPublisher(storage_state_path=sau_bili_state_file)

    with patch("asyncio.create_subprocess_exec") as mock_subprocess:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0
        mock_subprocess.return_value = mock_proc

        result = await pub.validate_login()

    assert result is True
    # Verify it called biliup renew
    assert mock_subprocess.call_count >= 1
    call_args = mock_subprocess.call_args[0]
    # call_args = [biliup_binary, "-u", cookie_path, "renew"]
    # Binary path contains "biliup" (e.g. biliup.exe)
    assert any("biliup" in arg for arg in call_args)
    assert "renew" in call_args


@pytest.mark.asyncio
async def test_sau_validate_login_fails_on_expired(sau_bili_state_file):
    """validate_login returns False when biliup renew fails."""
    from app.services.publish.sau_bilibili import SauBilibiliPublisher

    pub = SauBilibiliPublisher(storage_state_path=sau_bili_state_file)

    with patch("asyncio.create_subprocess_exec") as mock_subprocess:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error: token expired"))
        mock_proc.returncode = 1
        mock_subprocess.return_value = mock_proc

        result = await pub.validate_login()
        assert result is False


@pytest.mark.asyncio
async def test_sau_validate_login_missing_storage(tmp_path):
    """validate_login returns False when storage_state file doesn't exist."""
    from app.services.publish.sau_bilibili import SauBilibiliPublisher
    pub = SauBilibiliPublisher(storage_state_path=str(tmp_path / "missing.json"))
    result = await pub.validate_login()
    assert result is False


@pytest.mark.asyncio
async def test_sau_publish_missing_video(sau_bili_state_file):
    """publish returns error if video file doesn't exist."""
    from app.services.publish.sau_bilibili import SauBilibiliPublisher
    from app.services.publish.base import PublishFields
    pub = SauBilibiliPublisher(storage_state_path=sau_bili_state_file)
    result = await pub.publish(
        video_id=1,
        fields=PublishFields(title="Test"),
        video_file_path="/nonexistent/video.mp4",
    )
    assert result.success is False
    assert "不存在" in result.error_msg


@pytest.mark.asyncio
async def test_sau_publish_missing_storage(tmp_path):
    """publish returns needs_relogin if storage_state missing."""
    from app.services.publish.sau_bilibili import SauBilibiliPublisher
    from app.services.publish.base import PublishFields

    vpath = tmp_path / "v.mp4"
    vpath.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    pub = SauBilibiliPublisher(storage_state_path=str(tmp_path / "missing.json"))
    result = await pub.publish(
        video_id=1,
        fields=PublishFields(title="Test"),
        video_file_path=str(vpath),
    )
    assert result.success is False
    assert result.needs_relogin is True


@pytest.mark.asyncio
async def test_sau_publish_success(sau_bili_state_file, tmp_path):
    """publish returns success when biliup upload exits 0 with BV in output."""
    from app.services.publish.sau_bilibili import SauBilibiliPublisher
    from app.services.publish.base import PublishFields

    vpath = tmp_path / "v.mp4"
    vpath.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    pub = SauBilibiliPublisher(storage_state_path=sau_bili_state_file)

    with patch("asyncio.create_subprocess_exec") as mock_subprocess:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(
            b"[INFO] upload complete BV1abc123def\n",
            b"",
        ))
        mock_proc.returncode = 0
        mock_subprocess.return_value = mock_proc

        result = await pub.publish(
            video_id=1,
            fields=PublishFields(
                title="Test Title",
                description="Test Description",
                tags=["tag1", "tag2"],
                category_id="122",
            ),
            video_file_path=str(vpath),
        )

    assert result.success is True
    assert "BV1abc123def" in (result.platform_video_url or "")
    assert "bilibili.com" in (result.platform_video_url or "")


@pytest.mark.asyncio
async def test_sau_publish_failure(sau_bili_state_file, tmp_path):
    """publish returns error when biliup upload fails."""
    from app.services.publish.sau_bilibili import SauBilibiliPublisher
    from app.services.publish.base import PublishFields

    vpath = tmp_path / "v.mp4"
    vpath.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    pub = SauBilibiliPublisher(storage_state_path=sau_bili_state_file)

    with patch("asyncio.create_subprocess_exec") as mock_subprocess:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(
            b"",
            b"RuntimeError: token expired, please re-login",
        ))
        mock_proc.returncode = 1
        mock_subprocess.return_value = mock_proc

        result = await pub.publish(
            video_id=1,
            fields=PublishFields(title="Test"),
            video_file_path=str(vpath),
        )

    assert result.success is False
    assert result.needs_relogin is True


def test_sau_extract_bv_no_match():
    """_extract_bv_url returns None when no BV found in output."""
    from app.services.publish.sau_bilibili import SauBilibiliPublisher
    pub = SauBilibiliPublisher(storage_state_path="/fake")
    result = pub._extract_bv_url("no BV here", "also nothing", 1)
    assert result is None


def test_sau_extract_bv_with_match():
    """_extract_bv_url extracts BV from stdout."""
    from app.services.publish.sau_bilibili import SauBilibiliPublisher
    pub = SauBilibiliPublisher(storage_state_path="/fake")
    result = pub._extract_bv_url(
        "some output BV1qq2222xxx end", "", 1
    )
    assert result == "https://www.bilibili.com/video/BV1qq2222xxx"


def test_sau_extract_error_message():
    """_extract_error pulls the right error from combined output."""
    from app.services.publish.sau_bilibili import SauBilibiliPublisher
    pub = SauBilibiliPublisher(storage_state_path="/fake")
    error = pub._extract_error(
        "stdout line",
        "RuntimeError: Unknown Error\n╰─▶ invalid credentials for bilibili",
    )
    assert "invalid credentials" in error
