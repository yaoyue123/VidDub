"""Unit tests for SiliconFlow HTTP client (P4-10)."""
import os

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.siliconflow.client import (
    get_api_key,
    sf_post,
    sf_post_bytes,
    get_async_client,
    RetryableHTTPError,
)


def test_get_api_key_missing(monkeypatch):
    """无 API key 抛 RuntimeError."""
    monkeypatch.setattr("app.core.config.settings.siliconflow_api_key", "")
    with pytest.raises(RuntimeError, match="SILICONFLOW_API_KEY"):
        get_api_key()


def test_get_api_key_present(monkeypatch):
    """正常读取."""
    monkeypatch.setattr("app.core.config.settings.siliconflow_api_key", "sk-test-123")
    assert get_api_key() == "sk-test-123"


@pytest.mark.asyncio
async def test_sf_post_200(mock_sf_client):
    """200 响应直接返回，不重试."""
    resp = await sf_post(mock_sf_client, "chat/completions", json={"q": 1})
    assert resp.status_code == 200
    mock_sf_client.post.assert_awaited_once()
    args, kwargs = mock_sf_client.post.call_args
    assert "Authorization" in kwargs["headers"]
    assert kwargs["headers"]["Authorization"].startswith("Bearer ")
    assert "chat/completions" in args[0] or "chat/completions" in args[0]


@pytest.mark.asyncio
async def test_sf_post_429_retries_then_fails(monkeypatch):
    """429 触发重试 3 次后失败（reraise）."""
    # 强制等待时间为 0 加速测试
    monkeypatch.setattr(
        "app.services.siliconflow.client.wait_exponential",
        lambda **kw: lambda retry_state: 0.001,
    )

    response = MagicMock()
    response.status_code = 429
    response.text = '{"error": "rate limit"}'

    client = AsyncMock()
    client.post.return_value = response

    with pytest.raises(RetryableHTTPError):
        await sf_post(client, "audio/speech", json={})

    assert client.post.await_count == 3


@pytest.mark.asyncio
async def test_sf_post_500_retries(monkeypatch):
    """500 触发重试."""
    monkeypatch.setattr(
        "app.services.siliconflow.client.wait_exponential",
        lambda **kw: lambda retry_state: 0.001,
    )
    response = MagicMock()
    response.status_code = 500
    response.text = "Internal error"

    client = AsyncMock()
    client.post.return_value = response

    with pytest.raises(RetryableHTTPError):
        await sf_post(client, "chat/completions", json={})
    assert client.post.await_count == 3


@pytest.mark.asyncio
async def test_sf_post_400_raises_http_error(mock_sf_client):
    """400 (非重试) raise_for_status."""
    response = MagicMock()
    response.status_code = 400
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Bad Request", request=MagicMock(), response=response,
    )
    mock_sf_client.post.return_value = response

    with pytest.raises(httpx.HTTPStatusError):
        await sf_post(mock_sf_client, "audio/speech", json={})


@pytest.mark.asyncio
async def test_sf_post_bytes_returns_content(mock_sf_client):
    """返回 resp.content."""
    data = await sf_post_bytes(mock_sf_client, "audio/speech", json={})
    assert data == b"\x00\x01\x02\x03FAKE_AUDIO"


@pytest.mark.asyncio
async def test_sf_post_bytes_no_double_retry(monkeypatch):
    """CR-02: sf_post_bytes 不应再次重试 sf_post 已重试过的请求（避免 3×3=9 次）."""
    monkeypatch.setattr(
        "app.services.siliconflow.client.wait_exponential",
        lambda **kw: lambda retry_state: 0.001,
    )
    response = MagicMock()
    response.status_code = 429
    response.text = "rate limit"

    client = AsyncMock()
    client.post.return_value = response

    with pytest.raises(RetryableHTTPError):
        await sf_post_bytes(client, "audio/speech", json={})

    # sf_post 内部 3 次；若 sf_post_bytes 叠加，会是 3×3=9 次。
    assert client.post.await_count == 3, (
        f"expected 3 retries (single layer per D-04), got {client.post.await_count}"
    )


def test_get_async_client():
    client = get_async_client(timeout=10.0)
    assert isinstance(client, httpx.AsyncClient)
