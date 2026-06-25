"""Bilibili 扫码登录 (Phase 6, B4).

策略（D6-07, D6-02）：
- 优先使用官方 HTTP QR API（httpx），不启动 Playwright，速度快
- 二维码内容是 URL，本地用 `qrcode` 包生成 PNG 图片
- 轮询 poll endpoint，状态机映射 code → LoginStatus

API：
- 生成：GET https://passport.bilibili.com/x/passport-login/web/qrcode/generate
- 轮询：GET https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key=...
- 检测：GET https://api.bilibili.com/x/web-interface/nav（带 cookies，检查 data.isLogin）
"""
from __future__ import annotations

import io
import logging
from typing import Any, Optional

import httpx
import qrcode

from app.services.platform.base import (
    LOGIN_POLL_INTERVAL_SEC,
    LoginStatus,
    PlatformLoginBase,
)

logger = logging.getLogger(__name__)


BILI_QR_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
BILI_QR_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
BILI_NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
# Phase 6 fix: refresh_token → SESSDATA 兑换（必需，否则 cookies 取不到）
BILI_CORRESPOND_BASE = "https://www.bilibili.com/correspond/1/"

# 哔哩哔哩 poll code 含义
# 注：现代 API 用 86101 表示"未扫码"，86039 是旧版/部分文档遗留代码，两者都映射为 WAITING
BILI_POLL_CODES = {
    0: LoginStatus.SUCCESS,
    86038: LoginStatus.EXPIRED,
    86090: LoginStatus.SCANNED,        # 已扫码，等待确认
    86101: LoginStatus.WAITING,        # 未扫码（现代 API 主流）
    86039: LoginStatus.WAITING,        # 未扫码（旧版兼容）
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
}


class BilibiliLogin(PlatformLoginBase):
    platform_name = "bilibili"

    def __init__(self, storage_state_path: str) -> None:
        super().__init__(storage_state_path=storage_state_path)
        self._qrcode_key: Optional[str] = None
        self._last_cookies: Optional[dict[str, str]] = None

    # ── 启动扫码登录 ──

    async def start_qr_login(self) -> bytes:
        """调用 generate API → 拿到 url + qrcode_key → 用 qrcode 包生成 PNG."""
        async with httpx.AsyncClient(timeout=15.0, headers=DEFAULT_HEADERS) as client:
            resp = await client.get(BILI_QR_GENERATE_URL)
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"Bilibili generate failed: {data}")

        payload = data["data"]
        qr_url = payload["url"]
        self._qrcode_key = payload["qrcode_key"]
        self._mark_session_start()
        self._mark_qr_refreshed()

        # 用 qrcode 包把 URL 编码为 PNG bytes
        return self._encode_qr_png(qr_url)

    @staticmethod
    def _encode_qr_png(content: str) -> bytes:
        """用 qrcode 包生成 PNG 字节."""
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(content)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    # ── 轮询登录状态 ──

    async def poll_login_status(self) -> dict[str, Any]:
        if not self._qrcode_key:
            return {"status": LoginStatus.FAILED, "message": "未启动扫码登录"}

        if self.is_session_expired():
            return {"status": LoginStatus.TIMEOUT, "message": "5 分钟超时"}

        params = {"qrcode_key": self._qrcode_key}
        async with httpx.AsyncClient(timeout=10.0, headers=DEFAULT_HEADERS) as client:
            resp = await client.get(BILI_QR_POLL_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        inner = data.get("data", {}) or {}
        code = int(inner.get("code", -1))
        status = BILI_POLL_CODES.get(code, LoginStatus.FAILED)
        message = inner.get("message", "")

        # 调试日志（不打印任何敏感值，只打印 code/message/status）
        logger.info(
            "bilibili poll raw: top_code=%s inner_code=%s message=%r status=%s refresh_token=%s",
            data.get("code"), code, message, status,
            "yes" if inner.get("refresh_token") else "no",
        )

        result: dict[str, Any] = {"status": status, "message": message, "code": code}

        if status == LoginStatus.SUCCESS:
            # 先从 poll 响应的 Set-Cookie 提取（Bilibili 通常会在这里下发 SESSDATA）
            cookies = dict(resp.cookies)
            if not cookies:
                jar_cookies: dict[str, str] = {}
                for cookie in client.cookies.jar:
                    if cookie.domain and "bilibili.com" in cookie.domain:
                        jar_cookies[cookie.name] = cookie.value
                cookies = jar_cookies

            # Phase 6 fix: 如果 poll 没下发 cookies，用 refresh_token 走 correspond/1 兑换
            refresh_token = inner.get("refresh_token")
            if not cookies and refresh_token:
                logger.info("poll returned no cookies, exchanging refresh_token via correspond/1")
                try:
                    cookies = await self._exchange_refresh_token(refresh_token)
                except Exception as e:
                    logger.warning("refresh_token exchange failed: %s", e)

            result["cookies"] = cookies
            self._last_cookies = cookies
            # 尝试拉取用户信息
            try:
                user_info = await self._fetch_nav(cookies)
                result["user_info"] = user_info
            except Exception as e:
                logger.warning("fetch nav after login failed: %s", e)

            # 持久化 storage_state
            self._persist_storage_state(cookies, result.get("user_info"))

        return result

    async def _exchange_refresh_token(self, refresh_token: str) -> dict[str, str]:
        """访问 correspond/1/{refresh_token} 兑换 SESSDATA 等会话 cookies.

        Bilibili QR 登录在 poll 返回 code=0 后，某些场景下 Set-Cookie 不下发 SESSDATA，
        需要额外访问该 endpoint 才能拿到有效的会话 cookies。Referer/UA 必须带。
        """
        url = BILI_CORRESPOND_BASE + refresh_token
        async with httpx.AsyncClient(
            timeout=10.0,
            headers={
                **DEFAULT_HEADERS,
                "Referer": "https://www.bilibili.com/",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            # 提取所有 .bilibili.com 域 cookies
            cookies: dict[str, str] = {}
            for cookie in client.cookies.jar:
                if cookie.domain and "bilibili.com" in cookie.domain:
                    cookies[cookie.name] = cookie.value
            logger.info(
                "correspond/1 exchange done: got %d cookies, keys=%s",
                len(cookies), list(cookies.keys()),
            )
            return cookies

    # ── 登录态检测（使用 storage_state）──

    async def check_login_status(self) -> bool:
        state = self._load_storage_state()
        if not state:
            return False
        cookies = state.get("cookies", {})
        if not cookies:
            return False
        try:
            nav = await self._fetch_nav(cookies)
            return bool(nav.get("isLogin"))
        except Exception as e:
            logger.warning("check_login_status failed: %s", e)
            return False

    # ── 登出 ──

    async def logout(self) -> None:
        import os
        if os.path.exists(self.storage_state_path):
            try:
                os.remove(self.storage_state_path)
                logger.info("Bilibili logout: removed %s", self.storage_state_path)
            except OSError as e:
                logger.warning("Bilibili logout failed: %s", e)
        self._qrcode_key = None
        self._last_cookies = None
        self._session_start_ts = None

    # ── 内部辅助 ──

    async def _fetch_nav(self, cookies: dict[str, str]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0, headers=DEFAULT_HEADERS, cookies=cookies) as client:
            resp = await client.get(BILI_NAV_URL)
            resp.raise_for_status()
            data = resp.json()
        if data.get("code") != 0:
            return {"isLogin": False}
        inner = data.get("data", {})
        return {
            "isLogin": bool(inner.get("isLogin")),
            "uid": inner.get("mid"),
            "username": inner.get("uname"),
            "avatar": inner.get("face"),
            "vip_type": inner.get("vipType"),
            "level": inner.get("level_info", {}).get("current_level") if inner.get("level_info") else None,
        }

    def _load_storage_state(self) -> Optional[dict]:
        import json
        import os
        if not os.path.exists(self.storage_state_path):
            return None
        try:
            with open(self.storage_state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("load storage_state failed: %s", e)
            return None

    def _persist_storage_state(self, cookies: dict[str, str], user_info: Optional[dict]) -> None:
        import json
        import os
        import time
        state = {
            "platform": self.platform_name,
            "saved_at": time.time(),
            "cookies": cookies,
            "user_info": user_info or {},
        }
        os.makedirs(os.path.dirname(self.storage_state_path), exist_ok=True)
        tmp = self.storage_state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.storage_state_path)
        logger.info("Bilibili storage_state saved -> %s", self.storage_state_path)
