"""SiliconFlow HTTP client with tenacity retry (D-04).

约定：
- Bearer token 从 .env 的 SILICONFLOW_API_KEY 注入
- 429/500/502/503/504 触发重试（指数退避 2s→4s→8s，最多 3 次）
- 4xx (除 429) 直接 raise_for_status
- 日志中 Authorization 脱敏 (Threat T-04-05)
"""
import logging
from typing import Any, Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

# 重试触发的 HTTP 状态码
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class RetryableHTTPError(Exception):
    """抛此异常触发 tenacity 重试（封装 429/5xx）."""


def get_api_key() -> str:
    """Read SiliconFlow API Key from unified settings."""
    key = settings.siliconflow_api_key.strip()
    if not key:
        raise RuntimeError(
            "SILICONFLOW_API_KEY not set. "
            "请复制 backend/.env.example 为 backend/.env 并填入密钥 "
            "(https://cloud.siliconflow.cn/account/ak)"
        )
    return key


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_api_key()}"}


def _is_retryable_status(status_code: int) -> bool:
    return status_code in RETRYABLE_STATUS


# ── tenacity 装饰器（D-04） ──
_RETRY_POLICY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((RetryableHTTPError, httpx.TimeoutException)),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)


@_RETRY_POLICY
async def sf_post(
    client: httpx.AsyncClient,
    path: str,
    *,
    base_url: Optional[str] = None,
    **kwargs: Any,
) -> httpx.Response:
    """POST JSON/multipart 到 SiliconFlow，返回 httpx.Response.

    429/5xx 抛 RetryableHTTPError 触发重试；其他 4xx 直接 raise_for_status。
    """
    base = base_url or settings.siliconflow_base_url
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"

    logger.debug("sf_post → %s (base=%s key=%s...)", url, base, get_api_key()[:8])

    headers = kwargs.pop("headers", {}) or {}
    headers.update(_auth_headers())

    resp = await client.post(url, headers=headers, **kwargs)

    if _is_retryable_status(resp.status_code):
        body_tail = (resp.text or "")[:200]
        logger.warning(
            "SiliconFlow %s returned %d (retryable): %s",
            _redact_url(url), resp.status_code, body_tail,
        )
        raise RetryableHTTPError(f"HTTP {resp.status_code} from {path}: {body_tail}")

    resp.raise_for_status()
    return resp


async def sf_post_bytes(
    client: httpx.AsyncClient,
    path: str,
    *,
    base_url: Optional[str] = None,
    **kwargs: Any,
) -> bytes:
    """POST 并返回 resp.content（用于 TTS 二进制音频）.

    CR-02: 故意不加 @_RETRY_POLICY — sf_post 内部已重试（D-04: 3 次），
    在此再叠一层会变成 3×3=9 次，违反 D-04 且 hammer SiliconFlow。
    """
    resp = await sf_post(client, path, base_url=base_url, **kwargs)
    return resp.content


def get_async_client(timeout: float = 60.0) -> httpx.AsyncClient:
    """返回配置好 timeout 的 httpx.AsyncClient（调用方负责 close/aclose）."""
    return httpx.AsyncClient(timeout=timeout)


def _redact_url(url: str) -> str:
    """日志中脱敏 query string (避免 token 泄漏)."""
    if "?" in url:
        return url.split("?")[0] + "?<redacted>"
    return url
