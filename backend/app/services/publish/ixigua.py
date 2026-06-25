"""Ixigua (西瓜视频) publisher (Phase 7, B7).

策略 (D7-01, D7-04)：
- Playwright headed Chromium
- 加载 Phase 6 的 ixigua_storage_state.json
- 导航到 https://creator.ixigua.com/upload
- 类似 Bilibili 流程：上传 → 处理 → 填表 → 选 原创/转载 → 提交
- 转载时填原 YouTube URL
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any, Optional

from app.services.publish.base import (
    PlatformPublisher,
    PublishFields,
    PublishResult,
    UPLOAD_TIMEOUT_SEC,
    PROGRESS_POLL_INTERVAL,
)

logger = logging.getLogger(__name__)


IXIGUA_UPLOAD_URL = "https://creator.ixigua.com/upload"

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# 候选 selector — 西瓜视频创作平台 DOM 可能改版
IXIGUA_SELECTORS = {
    "file_input": [
        'input[type="file"][accept*="video"]',
        'input[type="file"]',
        '.upload input[type=file]',
    ],
    "title_input": [
        'input[placeholder*=标题]',
        '.title-input input',
        'input[name=title]',
    ],
    "desc_input": [
        'textarea[placeholder*=描述]',
        'textarea[placeholder*=简介]',
        '.desc-textarea textarea',
        '.ql-editor',
    ],
    "tag_input": [
        'input[placeholder*=标签]',
        '.tag-input input',
    ],
    "cover_input": [
        '.cover-upload input[type=file]',
        'input[type=file][accept*=image]',
    ],
    # 原创 / 转载 单选
    "copyright_original": [
        'xpath=//label[contains(text(),"原创")]',
        'xpath=//span[contains(text(),"原创")]',
        'input[value=original]',
    ],
    "copyright_repost": [
        'xpath=//label[contains(text(),"转载")]',
        'xpath=//span[contains(text(),"转载")]',
        'input[value=repost]',
    ],
    "source_url_input": [
        'input[placeholder*=来源]',
        'input[placeholder*=转载链接]',
        'xpath=//input[following-sibling::*[contains(text(),"来源")]]',
    ],
    "submit_button": [
        'button.publish-btn',
        'xpath=//button[contains(text(),"发布")]',
        'xpath=//button[contains(text(),"提交")]',
    ],
    "success_indicator": [
        'xpath=//*[contains(text(),"发布成功")]',
        'xpath=//*[contains(text(),"提交成功")]',
        '.success-tip',
    ],
}


class IxiguaPublisher(PlatformPublisher):
    platform = "ixigua"

    def __init__(self, storage_state_path: str, headless: bool = False,
                 upload_timeout: int = UPLOAD_TIMEOUT_SEC) -> None:
        self.storage_state_path = storage_state_path
        self.headless = headless
        self.upload_timeout = upload_timeout

    async def validate_login(self) -> bool:
        from app.services.platform.manager import get_login_manager
        try:
            login = get_login_manager().get("ixigua")
            return await login.check_login_status()
        except Exception as e:
            logger.warning("IxiguaPublisher validate_login: %s", e)
            return False

    async def publish(self, video_id: int, fields: PublishFields,
                      video_file_path: str,
                      progress_callback: Optional[Any] = None) -> PublishResult:
        if not os.path.exists(video_file_path):
            return PublishResult(success=False,
                                 error_msg=f"视频文件不存在: {video_file_path}")

        storage_state = self._load_storage_state_for_playwright()
        if storage_state is None:
            return PublishResult(success=False,
                                 error_msg="未登录西瓜视频 (storage_state 缺失)",
                                 needs_relogin=True)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return PublishResult(success=False, error_msg="playwright 未安装")

        screenshot_path: Optional[str] = None

        async def _progress(stage: str, pct: float):
            if progress_callback:
                try:
                    await progress_callback(stage, pct)
                except Exception:
                    pass

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                ctx = await browser.new_context(
                    user_agent=DEFAULT_UA,
                    viewport={"width": 1280, "height": 900},
                    locale="zh-CN",
                    storage_state=storage_state,
                )
                page = await ctx.new_page()
                await _progress("loading", 0)
                await page.goto(IXIGUA_UPLOAD_URL, wait_until="domcontentloaded",
                                timeout=30000)
                await page.wait_for_timeout(2500)

                # 登录态检测：跳到登录页则视为 needs_relogin
                if "/login" in page.url or "passport" in page.url:
                    return PublishResult(success=False,
                                         error_msg="登录态已过期，请重新扫码",
                                         needs_relogin=True)

                # 1. 上传
                await _progress("uploading", 5)
                file_input = await self._find_first(page, IXIGUA_SELECTORS["file_input"])
                if not file_input:
                    screenshot_path = await self._screenshot(page, video_id, "no_file_input")
                    return PublishResult(success=False,
                                         error_msg="找不到视频上传 input",
                                         screenshot_path=screenshot_path)
                await file_input.set_input_files(video_file_path)

                # 2. 等待上传 + 处理
                await self._wait_for_processing(page, video_id, _progress)

                # 3. 填表
                await _progress("filling", 80)
                await self._fill_text(page, IXIGUA_SELECTORS["title_input"],
                                      self._safe_text(fields.title, 30))
                await self._fill_text(page, IXIGUA_SELECTORS["desc_input"],
                                      self._safe_text(fields.description, 2000))
                await self._fill_tags(page, fields.tags)
                if fields.cover_path and os.path.exists(fields.cover_path):
                    await self._fill_cover(page, fields.cover_path)

                # 4. 选 原创/转载
                cp_type = fields.copyright_type or "repost"
                await self._select_copyright(page, cp_type)
                if cp_type == "repost" and fields.source_url:
                    await self._fill_source_url(page, fields.source_url)

                # 5. 提交
                await _progress("submitting", 90)
                submit_btn = await self._find_first(page, IXIGUA_SELECTORS["submit_button"])
                if not submit_btn:
                    screenshot_path = await self._screenshot(page, video_id, "no_submit")
                    return PublishResult(success=False,
                                         error_msg="找不到提交按钮",
                                         screenshot_path=screenshot_path)
                await submit_btn.click()

                ok = await self._wait_success(page)
                if not ok:
                    screenshot_path = await self._screenshot(page, video_id, "no_success")
                    return PublishResult(success=False,
                                         error_msg="提交后未检测到成功页",
                                         screenshot_path=screenshot_path)

                platform_url = await self._extract_published_url(page)
                await _progress("completed", 100)
                return PublishResult(success=True, platform_video_url=platform_url)

        except Exception as e:
            logger.error("IxiguaPublisher error: %s", e, exc_info=True)
            return PublishResult(success=False, error_msg=str(e),
                                 screenshot_path=screenshot_path)

    # ── 内部辅助 ──

    def _load_storage_state_for_playwright(self) -> Optional[dict]:
        if not os.path.exists(self.storage_state_path):
            return None
        import json
        try:
            with open(self.storage_state_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return None
        cookies_raw = raw.get("cookies", {})
        cookies_list = []
        if isinstance(cookies_raw, dict):
            for name, value in cookies_raw.items():
                cookies_list.append({
                    "name": name,
                    "value": str(value),
                    "domain": ".ixigua.com",
                    "path": "/",
                })
        elif isinstance(cookies_raw, list):
            cookies_list = cookies_raw
        return {"cookies": cookies_list, "origins": []}

    async def _find_first(self, page, selectors: list[str]):
        for sel in selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    return elem
            except Exception:
                continue
        return None

    async def _fill_text(self, page, selectors: list[str], text: str) -> None:
        elem = await self._find_first(page, selectors)
        if elem:
            try:
                await elem.click()
                await elem.fill(text)
            except Exception as e:
                logger.warning("fill_text failed: %s", e)

    async def _fill_tags(self, page, tags: list[str]) -> None:
        tags = [t for t in tags if t][:10]
        elem = await self._find_first(page, IXIGUA_SELECTORS["tag_input"])
        if not elem:
            return
        try:
            await elem.click()
            for t in tags:
                try:
                    await elem.fill(t)
                    await elem.press("Enter")
                except Exception:
                    continue
        except Exception as e:
            logger.warning("ixigua fill tags: %s", e)

    async def _fill_cover(self, page, cover_path: str) -> None:
        elem = await self._find_first(page, IXIGUA_SELECTORS["cover_input"])
        if elem:
            try:
                await elem.set_input_files(cover_path)
            except Exception as e:
                logger.warning("ixigua fill cover: %s", e)

    async def _select_copyright(self, page, cp_type: str) -> None:
        sels = (IXIGUA_SELECTORS["copyright_original"] if cp_type == "original"
                else IXIGUA_SELECTORS["copyright_repost"])
        elem = await self._find_first(page, sels)
        if elem:
            try:
                await elem.click()
            except Exception as e:
                logger.warning("ixigua select copyright: %s", e)

    async def _fill_source_url(self, page, url: str) -> None:
        elem = await self._find_first(page, IXIGUA_SELECTORS["source_url_input"])
        if elem:
            try:
                await elem.fill(url)
            except Exception as e:
                logger.warning("ixigua fill source: %s", e)

    async def _wait_for_processing(self, page, video_id: int,
                                    _progress) -> None:
        deadline = time.time() + self.upload_timeout
        last_pct = 0.0
        while time.time() < deadline:
            pct = None
            for sel in ['.upload-progress', '.video-process',
                        'xpath=//div[contains(@class,"progress")]',
                        '.text-success']:
                try:
                    elem = await page.query_selector(sel)
                    if elem:
                        text = (await elem.inner_text()) or ""
                        text = text.strip()
                        if "%" in text:
                            try:
                                pct = float(text.replace("%", "").strip())
                                break
                            except ValueError:
                                continue
                        if "完成" in text or "成功" in text:
                            pct = 100.0
                            break
                except Exception:
                    continue
            if pct is None:
                pct = min(99.0, last_pct + 1.0)
            last_pct = pct
            await _progress("processing", 50 + pct / 2)
            if pct >= 100.0:
                return
            await asyncio.sleep(PROGRESS_POLL_INTERVAL)

    async def _wait_success(self, page, timeout_sec: int = 60) -> bool:
        for sel in IXIGUA_SELECTORS["success_indicator"]:
            try:
                await page.wait_for_selector(sel, timeout=timeout_sec * 1000)
                return True
            except Exception:
                continue
        # 兜底：URL 变化到管理页
        try:
            await page.wait_for_url("**/creator.ixigua.com/main**", timeout=20000)
            return True
        except Exception:
            return False

    async def _screenshot(self, page, video_id: int, tag: str) -> str:
        try:
            os.makedirs("backend/data/publish_debug", exist_ok=True)
            path = os.path.abspath(os.path.join(
                "backend/data/publish_debug",
                f"ixigua_v{video_id}_{tag}_{int(time.time())}.png",
            ))
            await page.screenshot(path=path, full_page=True)
            return path
        except Exception as e:
            logger.warning("ixigua screenshot failed: %s", e)
            return ""

    async def _extract_published_url(self, page) -> Optional[str]:
        try:
            content = await page.content()
            m = re.search(r'ixigua\.com/(\d{6,})', content)
            if m:
                return f"https://www.ixigua.com/{m.group(1)}"
            return page.url
        except Exception:
            return None
