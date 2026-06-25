"""Phase 6 平台登录 API.

路由：
- POST   /api/platform/{platform}/login/start  → 启动扫码登录，返回 qr_image_base64 + expires_at
- GET    /api/platform/{platform}/login/poll   → 轮询登录状态
- GET    /api/platform/{platform}/login/status → 查询当前是否已登录（基于 storage_state）
- POST   /api/platform/{platform}/logout       → 清除登录态
- GET    /api/platform/{platform}/check        → 主动检测登录态是否过期
- GET    /api/platform/state                   → 返回所有平台登录态总览（Dashboard 用）

WebSocket 事件：
- platform_qr_update {platform, qr_image_base64, expires_at}
- platform_login_status {platform, status, user_info?}
- platform_login_expired {platform}
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.websocket import manager as ws_manager
from app.services.platform.base import (
    LOGIN_TIMEOUT_SEC,
    QR_REFRESH_INTERVAL_SEC,
    LoginStatus,
)
from app.services.platform.manager import get_login_manager

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──

class QrStartResponse(BaseModel):
    platform: str
    qr_image_base64: str
    expires_at: float  # epoch
    message: Optional[str] = None


class LoginStatusResponse(BaseModel):
    platform: str
    status: str
    user_info: Optional[dict[str, Any]] = None
    message: Optional[str] = None
    cookies: Optional[dict[str, Any]] = None  # 仅 success 时返回（用于调试，生产可脱敏）


class CheckResponse(BaseModel):
    platform: str
    logged_in: bool
    expired: bool
    user_info: Optional[dict[str, Any]] = None


class LogoutResponse(BaseModel):
    platform: str
    success: bool
    message: Optional[str] = None


class PlatformStateItem(BaseModel):
    platform: str
    display_name: str
    logged_in: bool
    user_info: Optional[dict[str, Any]] = None


class AllStateResponse(BaseModel):
    platforms: list[PlatformStateItem]


# 平台中文显示名 (v3.2 — 新增 douyin)
PLATFORM_DISPLAY_NAMES = {
    "douyin": "抖音",
    "bilibili": "哔哩哔哩",
    "ixigua": "西瓜视频",
}

# SAU-native platforms (not managed by you2bili's LoginManager)
# These use SAU's own cookie format at social-auto-upload/cookies/
_SAU_NATIVE_PLATFORMS = {"douyin"}


def _validate_platform(platform: str) -> None:
    if platform not in PLATFORM_DISPLAY_NAMES:
        raise HTTPException(status_code=404, detail=f"未知平台: {platform}")


# ── 启动扫码登录 ──

@router.post("/{platform}/login/start", response_model=QrStartResponse)
async def start_login(platform: str) -> QrStartResponse:
    """启动扫码登录.

    返回 base64 PNG 二维码图片 + 过期时间戳。
    后端同时启动一个后台 task：每 30 秒推送最新二维码（QR 刷新）+
    每 2 秒轮询登录状态，成功 / 失败 / 超时都会通过 WebSocket 推送。
    """
    _validate_platform(platform)
    manager = get_login_manager()
    login = manager.get(platform)

    try:
        qr_bytes = await login.start_qr_login()
    except Exception as e:
        logger.error("start_qr_login failed for %s: %s", platform, e)
        # 区分 Playwright 启动失败
        msg = str(e)
        status_code = 503 if "Playwright" in msg or "playwright" in msg else 500
        raise HTTPException(status_code=status_code, detail=f"启动登录失败：{msg}")

    b64 = base64.b64encode(qr_bytes).decode("ascii")
    expires_at = time.time() + LOGIN_TIMEOUT_SEC

    # 启动后台 polling task（幂等：相同平台正在跑则跳过）
    task_key = f"platform_login_{platform}"
    if not _is_polling_running(task_key):
        asyncio.create_task(_login_poll_loop(platform, task_key))

    # 立即推送一次 QR
    await ws_manager.broadcast({
        "type": "platform_qr_update",
        "data": {
            "platform": platform,
            "qr_image_base64": b64,
            "expires_at": expires_at,
        },
    })

    return QrStartResponse(
        platform=platform,
        qr_image_base64=b64,
        expires_at=expires_at,
    )


# ── 轮询状态（HTTP 短轮询，前端备用）──

@router.get("/{platform}/login/poll", response_model=LoginStatusResponse)
async def poll_login(platform: str) -> LoginStatusResponse:
    _validate_platform(platform)
    manager = get_login_manager()
    login = manager.get(platform)
    result = await login.poll_login_status()
    return LoginStatusResponse(
        platform=platform,
        status=result.get("status", LoginStatus.FAILED),
        message=result.get("message"),
        user_info=result.get("user_info"),
        cookies=result.get("cookies"),
    )


# ── 查询当前登录态（仅查 storage_state，不调网络）──

@router.get("/{platform}/login/status", response_model=LoginStatusResponse)
async def login_status(platform: str) -> LoginStatusResponse:
    _validate_platform(platform)
    manager = get_login_manager()

    state = manager.load_storage_state(platform)
    if not state:
        return LoginStatusResponse(
            platform=platform,
            status="not_logged_in",
            message="未登录",
        )
    return LoginStatusResponse(
        platform=platform,
        status="logged_in",
        user_info=state.get("user_info"),
        message="已登录（基于本地 storage_state）",
    )


# ── 主动检测过期 ──

@router.get("/{platform}/check", response_model=CheckResponse)
async def check_login(platform: str) -> CheckResponse:
    _validate_platform(platform)
    manager = get_login_manager()
    login = manager.get(platform)

    # check_login_status 内部使用 httpx + cookies，无需启动 Playwright
    try:
        logged_in = await login.check_login_status()
    except Exception as e:
        logger.error("check_login_status failed: %s", e)
        return CheckResponse(
            platform=platform,
            logged_in=False,
            expired=True,
            message=str(e),  # message 字段不在 schema，但被 Pydantic 默认忽略
        )

    state = manager.load_storage_state(platform)
    user_info = state.get("user_info") if state else None
    expired = not logged_in and bool(state)

    if expired:
        await ws_manager.broadcast({
            "type": "platform_login_expired",
            "data": {"platform": platform},
        })

    return CheckResponse(
        platform=platform,
        logged_in=logged_in,
        expired=expired,
        user_info=user_info,
    )


# ── 登出 ──

@router.post("/{platform}/logout", response_model=LogoutResponse)
async def logout(platform: str) -> LogoutResponse:
    _validate_platform(platform)
    manager = get_login_manager()
    login = manager.get(platform)
    try:
        await login.logout()
        await ws_manager.broadcast({
            "type": "platform_login_status",
            "data": {"platform": platform, "status": "logged_out"},
        })
        return LogoutResponse(platform=platform, success=True, message="已登出")
    except Exception as e:
        return LogoutResponse(platform=platform, success=False, message=str(e))


# ── Dashboard 总览 ──

@router.get("/state", response_model=AllStateResponse)
async def all_state() -> AllStateResponse:
    """返回所有支持平台的登录态总览（Dashboard 卡片用）."""
    import os as _os
    manager = get_login_manager()
    items: list[PlatformStateItem] = []
    for pf, name in PLATFORM_DISPLAY_NAMES.items():
        if pf in _SAU_NATIVE_PLATFORMS:
            # SAU-native platforms: check account file existence
            _sau_dir = _os.path.normpath(
                _os.path.join(_os.path.dirname(__file__), "..", "..", "..", "social-auto-upload")
            )
            account_file = _os.path.join(_sau_dir, "cookies", f"douyin_you2bili.json")
            logged_in = _os.path.exists(account_file)
            items.append(PlatformStateItem(
                platform=pf, display_name=name, logged_in=logged_in,
            ))
        else:
            state = manager.load_storage_state(pf)
            if state and state.get("cookies"):
                items.append(PlatformStateItem(
                    platform=pf,
                    display_name=name,
                    logged_in=True,
                    user_info=state.get("user_info"),
                ))
            else:
                items.append(PlatformStateItem(
                    platform=pf, display_name=name, logged_in=False,
                ))
    return AllStateResponse(platforms=items)


# ── 后台轮询 task ──

# 简易全局注册表（进程内）
_polling_tasks: dict[str, asyncio.Task] = {}


def _is_polling_running(task_key: str) -> bool:
    t = _polling_tasks.get(task_key)
    return t is not None and not t.done()


async def _login_poll_loop(platform: str, task_key: str) -> None:
    """后台轮询登录状态 + 定期刷新 QR."""
    try:
        manager = get_login_manager()
        login = manager.get(platform)

        while True:
            await asyncio.sleep(2)
            if login.is_session_expired():
                await ws_manager.broadcast({
                    "type": "platform_login_status",
                    "data": {
                        "platform": platform,
                        "status": LoginStatus.TIMEOUT,
                        "message": "5 分钟超时",
                    },
                })
                break

            # 定期刷新 QR
            if login.needs_qr_refresh():
                try:
                    qr_bytes = await login.start_qr_login()
                    b64 = base64.b64encode(qr_bytes).decode("ascii")
                    await ws_manager.broadcast({
                        "type": "platform_qr_update",
                        "data": {
                            "platform": platform,
                            "qr_image_base64": b64,
                            "expires_at": time.time() + LOGIN_TIMEOUT_SEC,
                        },
                    })
                except Exception as e:
                    logger.warning("QR refresh failed for %s: %s", platform, e)

            # 轮询状态
            result = await login.poll_login_status()
            status = result.get("status")
            await ws_manager.broadcast({
                "type": "platform_login_status",
                "data": {
                    "platform": platform,
                    "status": status,
                    "message": result.get("message"),
                    "user_info": result.get("user_info"),
                },
            })

            if status in (LoginStatus.SUCCESS, LoginStatus.FAILED, LoginStatus.TIMEOUT):
                break
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("login poll loop crashed for %s: %s", platform, e, exc_info=True)
    finally:
        _polling_tasks.pop(task_key, None)
