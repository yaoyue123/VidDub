"""Ixigua (西瓜视频) 扫码登录 (Phase 6, B5).

西瓜视频没有公开稳定的 QR HTTP API（参考 D6-07 兜底策略），
使用 Playwright headed Chromium 模拟登录流程：
1. 启动 headed Chromium（D6-03 用户选择 headed 模式）
2. 访问 https://www.ixigua.com/ → 触发登录弹窗
3. 截屏二维码区域 → base64 推送前端
4. 轮询页面 URL / DOM 判断登录成功
5. storage_state 持久化

Playwright 启动可能失败（无 GUI / 未安装 browser）：
- 启动失败时抛出 PlatformLoginError，由 API 层返回 503 提示用户检查环境。
- 不影响 storage_state 加载与 check_login_status（后者用 httpx 检测）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional

import httpx

from app.services.platform.base import (
    LOGIN_POLL_INTERVAL_SEC,
    LoginStatus,
    PlatformLoginBase,
)

logger = logging.getLogger(__name__)


IXIGUA_HOME = "https://www.ixigua.com/"
IXIGUA_USER_API = "https://www.ixigua.com/api/user/info/self/"

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class PlatformLoginError(RuntimeError):
    """登录器初始化失败（如 Playwright 缺失）."""


class IxiguaLogin(PlatformLoginBase):
    platform_name = "ixigua"

    def __init__(self, storage_state_path: str, headless: bool = False) -> None:
        super().__init__(storage_state_path=storage_state_path)
        # D6-03：默认 headed 模式
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._page = None
        self._lock = asyncio.Lock()

    # ── 启动扫码登录 ──

    async def start_qr_login(self) -> bytes:
        """启动 Playwright → 访问主页 → 触发登录弹窗 → 截屏二维码区域."""
        async with self._lock:
            await self._ensure_browser_open()
            page = self._page

            try:
                await page.goto(IXIGUA_HOME, wait_until="domcontentloaded", timeout=30000)
                # 点击"登录"按钮（西瓜视频主页右上角，selector 可能随版本变）
                # 先尝试常见 selector，失败则忽略（部分用户已直接看到登录弹窗）
                clicked = False
                for sel in [
                    'xpath=//button[contains(text(), "登录")]',
                    'xpath=//div[contains(@class, "login") and contains(text(), "登录")]',
                    'xpath=//a[contains(text(), "登录")]',
                    '.login-btn',
                ]:
                    try:
                        elem = await page.wait_for_selector(sel, timeout=2000)
                        if elem:
                            await elem.click()
                            clicked = True
                            break
                    except Exception:
                        continue
                # 等待登录弹窗 / iframe 出现（二维码通常在 iframe 内或 modal 内）
                await page.wait_for_timeout(1500)
            except Exception as e:
                logger.warning("Ixigua start_qr_login navigation: %s", e)

            self._mark_session_start()
            self._mark_qr_refreshed()
            return await self._capture_qr_screenshot()

    async def _capture_qr_screenshot(self) -> bytes:
        """截取二维码区域（或整页兜底）."""
        page = self._page
        if page is None:
            raise PlatformLoginError("Playwright page not initialized")

        # 尝试常见二维码 selector
        candidates = [
            'iframe[src*="login"]',
            '.qrcode-img',
            'img[src*="qrcode"]',
            'canvas',
            'div[class*="qr"]',
        ]
        for sel in candidates:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    return await elem.screenshot(type="png")
            except Exception:
                continue

        # 兜底：截整页
        try:
            return await page.screenshot(type="png", full_page=False)
        except Exception as e:
            raise PlatformLoginError(f"Screenshot failed: {e}") from e

    # ── 轮询登录状态 ──

    async def poll_login_status(self) -> dict[str, Any]:
        if self._page is None:
            return {"status": LoginStatus.FAILED, "message": "Playwright 未启动"}

        if self.is_session_expired():
            return {"status": LoginStatus.TIMEOUT, "message": "5 分钟超时"}

        page = self._page
        try:
            # 检测 1：URL 跳转（登录成功通常 URL 不再带 login 参数或跳回首页）
            current_url = page.url
            cookies = await page.context.cookies()

            # 检测 2：查找登录后才会出现的用户菜单元素
            logged_in_selectors = [
                '.user-avatar',
                '.avatar-img',
                'xpath=//div[contains(@class, "user-name")]',
                'xpath=//a[contains(@href, "/user/self")]',
            ]
            for sel in logged_in_selectors:
                try:
                    elem = await page.query_selector(sel)
                    if elem:
                        # 提取 cookies 并持久化
                        cookie_dict = {c["name"]: c["value"] for c in cookies if "ixigua" in c.get("domain", "")}
                        user_info = await self._extract_user_info(page)
                        state = {
                            "platform": self.platform_name,
                            "saved_at": time.time(),
                            "cookies": cookie_dict,
                            "user_info": user_info,
                            "url_at_success": current_url,
                        }
                        self._persist_storage_state(state)
                        return {
                            "status": LoginStatus.SUCCESS,
                            "cookies": cookie_dict,
                            "user_info": user_info,
                            "message": "登录成功",
                        }
                except Exception:
                    continue

            # 未登录：检查 QR 区域是否仍存在
            qr_present = False
            for sel in ['iframe[src*="login"]', '.qrcode-img', 'img[src*="qrcode"]', 'canvas']:
                try:
                    elem = await page.query_selector(sel)
                    if elem:
                        qr_present = True
                        break
                except Exception:
                    continue

            # 简单状态机：QR 还在 → waiting；不在且无登录 → 推断 scanned 或 expired
            if qr_present:
                # 检查是否有"已扫描"提示
                try:
                    body_text = await page.inner_text("body")
                    if "扫描成功" in body_text or "已扫描" in body_text or "确认" in body_text:
                        return {"status": LoginStatus.SCANNED, "message": "已扫码，等待确认"}
                except Exception:
                    pass
                return {"status": LoginStatus.WAITING, "message": "等待扫码"}

            # QR 不见了，可能是过期
            return {"status": LoginStatus.EXPIRED, "message": "二维码可能已过期"}

        except Exception as e:
            logger.error("Ixigua poll error: %s", e)
            return {"status": LoginStatus.FAILED, "message": str(e)}

    # ── 登录态检测（httpx + storage_state，不启动浏览器）──

    async def check_login_status(self) -> bool:
        state = self._load_storage_state()
        if not state:
            return False
        cookies = state.get("cookies", {})
        if not cookies:
            return False
        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                headers={"User-Agent": DEFAULT_UA, "Referer": IXIGUA_HOME},
                cookies=cookies,
            ) as client:
                resp = await client.get(IXIGUA_HOME)
                text = resp.text
                # 西瓜视频登录态检测启发式：
                # - 已登录时首页 HTML 中会包含用户名或 user_id JSON
                # - 未登录时通常包含 "login" 按钮文案但无 user 信息
                if resp.status_code != 200:
                    return False
                # 从 HTML 中提取 __INITIAL_STATE__ 或类似 store 数据
                # 退化策略：搜常见登录态字段
                if '"isLogin":true' in text or '"user_id"' in text:
                    return True
                # 如果有保存的 user_info 但页面无登录标志，认为是过期
                return False
        except Exception as e:
            logger.warning("Ixigua check_login_status failed: %s", e)
            return False

    # ── 登出 ──

    async def logout(self) -> None:
        if os.path.exists(self.storage_state_path):
            try:
                os.remove(self.storage_state_path)
                logger.info("Ixigua logout: removed %s", self.storage_state_path)
            except OSError as e:
                logger.warning("Ixigua logout failed: %s", e)
        await self._close_browser()
        self._session_start_ts = None

    # ── Playwright 浏览器管理 ──

    async def _ensure_browser_open(self) -> None:
        """懒加载 Playwright + Chromium (headed)."""
        if self._page is not None:
            return

        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise PlatformLoginError(
                "playwright 未安装。请运行 `pip install playwright` 然后 `playwright install chromium`"
            ) from e

        # 加载已有 storage_state
        context_kwargs = {
            "user_agent": DEFAULT_UA,
            "viewport": {"width": 1280, "height": 800},
            "locale": "zh-CN",
        }
        existing_state = self._load_storage_state()
        if existing_state and existing_state.get("cookies"):
            # Playwright 接受 storage_state 文件路径或 dict
            # 这里传 dict 形式：只接受 {cookies: [...], origins: [...]}
            # 我们的格式略有差异，转换一下
            context_kwargs["storage_state"] = self._convert_state_for_playwright(existing_state)

        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._page = await self._browser.new_page(**context_kwargs)
            logger.info("Ixigua Playwright browser opened (headless=%s)", self.headless)
        except Exception as e:
            # 清理已启动但失败的资源
            await self._close_browser()
            raise PlatformLoginError(f"Playwright 启动失败：{e}") from e

    @staticmethod
    def _convert_state_for_playwright(state: dict) -> dict:
        """把我们的 storage_state 格式转换为 Playwright 期望的格式."""
        raw_cookies = state.get("cookies", {})
        # raw_cookies 可能是 dict {name: value}（我们自己存的）或 list[{...}]（Playwright 原生）
        cookies_list = []
        if isinstance(raw_cookies, dict):
            for name, value in raw_cookies.items():
                cookies_list.append({
                    "name": name,
                    "value": str(value),
                    "domain": ".ixigua.com",
                    "path": "/",
                })
        elif isinstance(raw_cookies, list):
            cookies_list = raw_cookies
        return {"cookies": cookies_list, "origins": []}

    async def _extract_user_info(self, page) -> dict[str, Any]:
        """从已登录页面提取用户信息（best-effort）."""
        info: dict[str, Any] = {}
        try:
            # 尝试从 localStorage / window 拉取
            for expr, key in [
                ("window.localStorage.getItem('user_info')", "user_info"),
                ("window.__INITIAL_STATE__?.user?.info", "initial_state_user"),
            ]:
                try:
                    val = await page.evaluate(expr)
                    if val:
                        if isinstance(val, str):
                            try:
                                val = json.loads(val)
                            except json.JSONDecodeError:
                                pass
                        if isinstance(val, dict):
                            info.update({
                                "uid": val.get("user_id") or val.get("uid"),
                                "username": val.get("name") or val.get("username") or val.get("uname"),
                                "avatar": val.get("avatar_url") or val.get("avatar"),
                            })
                            break
                except Exception:
                    continue
        except Exception as e:
            logger.debug("extract_user_info: %s", e)

        info.setdefault("source", "ixigua_web")
        return info

    def _load_storage_state(self) -> Optional[dict]:
        if not os.path.exists(self.storage_state_path):
            return None
        try:
            with open(self.storage_state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Ixigua load storage_state failed: %s", e)
            return None

    def _persist_storage_state(self, state: dict) -> None:
        os.makedirs(os.path.dirname(self.storage_state_path), exist_ok=True)
        tmp = self.storage_state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.storage_state_path)
        logger.info("Ixigua storage_state saved -> %s", self.storage_state_path)

    async def _close_browser(self) -> None:
        try:
            if self._page:
                await self._page.close()
        except Exception:
            pass
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._browser = None
        self._playwright = None
