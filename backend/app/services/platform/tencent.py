"""Tencent (WeChat Channels) login via SAU-native qrcode_callback.

Spawns tencent_setup(handle=True, qrcode_callback=...) in a background
asyncio task. SAU writes the QR PNG to disk; we forward the bytes to
the frontend via the platform login API.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Optional

from app.services.platform.base import LoginStatus, PlatformLoginBase

logger = logging.getLogger(__name__)

_SAU_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "social-auto-upload")
)
if os.path.isdir(_SAU_DIR) and _SAU_DIR not in sys.path:
    sys.path.insert(0, _SAU_DIR)


class TencentLogin(PlatformLoginBase):
    platform_name = "tencent"

    def __init__(self, storage_state_path: str) -> None:
        super().__init__(storage_state_path=storage_state_path)
        self._latest_qr_bytes: Optional[bytes] = None
        self._login_task: Optional[asyncio.Task] = None
        self._final_status: dict[str, Any] = {}

    async def start_qr_login(self) -> bytes:
        if self._login_task and not self._login_task.done() and self._latest_qr_bytes:
            return self._latest_qr_bytes

        self._latest_qr_bytes = None
        self._final_status = {}
        self._mark_session_start()
        self._mark_qr_refreshed()

        def _qrcode_callback(payload: dict) -> None:
            path = payload.get("image_path")
            if path and os.path.exists(path):
                with open(path, "rb") as f:
                    self._latest_qr_bytes = f.read()
            self._mark_qr_refreshed()

        async def _runner():
            try:
                from uploader.tencent_uploader.main import tencent_setup
                result = await tencent_setup(
                    self.storage_state_path,
                    handle=True,
                    return_detail=True,
                    qrcode_callback=_qrcode_callback,
                    headless=True,
                )
                self._final_status = result or {}
            except Exception as e:
                logger.error("tencent SAU setup crashed: %s", e)
                self._final_status = {"success": False, "message": str(e)}

        self._login_task = asyncio.create_task(_runner())

        for _ in range(50):
            if self._latest_qr_bytes:
                return self._latest_qr_bytes
            await asyncio.sleep(0.1)

        if not self._latest_qr_bytes:
            raise RuntimeError("微信视频号二维码生成超时（5s）")
        return self._latest_qr_bytes

    async def poll_login_status(self) -> dict[str, Any]:
        if self.is_session_expired():
            return {"status": LoginStatus.TIMEOUT, "message": "5 分钟超时"}
        if not self._login_task:
            return {"status": LoginStatus.FAILED, "message": "未启动扫码登录"}
        if self._login_task.done():
            success = bool(self._final_status.get("success"))
            return {
                "status": LoginStatus.SUCCESS if success else LoginStatus.FAILED,
                "message": self._final_status.get("message", ""),
                "user_info": self._final_status.get("user_info"),
            }
        return {"status": LoginStatus.WAITING, "message": "等待扫码"}

    async def check_login_status(self) -> bool:
        if not os.path.exists(self.storage_state_path):
            return False
        try:
            from uploader.tencent_uploader.main import tencent_setup
            result = await tencent_setup(
                self.storage_state_path, handle=False,
                return_detail=True, headless=True,
            )
            return bool(result.get("success"))
        except Exception as e:
            logger.warning("tencent check_login_status: %s", e)
            return False

    async def logout(self) -> None:
        if self._login_task and not self._login_task.done():
            self._login_task.cancel()
        if os.path.exists(self.storage_state_path):
            try:
                os.remove(self.storage_state_path)
            except OSError:
                pass
        self._latest_qr_bytes = None
        self._session_start_ts = None
