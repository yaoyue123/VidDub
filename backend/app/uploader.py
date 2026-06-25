"""
Platform upload services.

Bilibili: Full HTTP API (preupload → chunk upload → submit)
Xigua:  Playwright browser automation (no public HTTP API for video)
"""

import asyncio
import base64
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Shared types ──

BILI_CATEGORIES = {
    122: "野生技术协会",
    95: "数码",
    207: "资讯",
    174: "生活",
    21: "日常",
    4: "游戏",
    119: "动物圈",
    129: "舞蹈",
    130: "音乐",
    155: "娱乐",
    165: "汽车",
    181: "影视",
    188: "动漫",
    211: "美食",
    223: "知识",
    251: "自媒体",
}

BILI_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


# ── Bilibili Uploader ──


@dataclass
class BiliUploadResult:
    """Result of a Bilibili upload."""
    bvid: str = ""
    aid: int = 0
    success: bool = False
    error: str = ""


@dataclass
class BiliCredential:
    """Bilibili cookie credential."""
    sessdata: str = ""
    bili_jct: str = ""
    dedeuserid: str = ""


class BilibiliUploader:
    """Upload videos to Bilibili via web API (cookie-based)."""

    PREUPLOAD_URL = "https://member.bilibili.com/preupload"
    COVER_UPLOAD_URL = "https://member.bilibili.com/x/vu/web/cover/up"
    SUBMIT_URL = "https://member.bilibili.com/x/vu/web/add"

    def __init__(self, credential: BiliCredential):
        self.cred = credential
        self.client = httpx.AsyncClient(
            cookies={
                "SESSDATA": credential.sessdata,
                "bili_jct": credential.bili_jct,
                "DedeUserID": credential.dedeuserid,
            },
            headers={
                "User-Agent": BILI_UA,
                "Referer": "https://member.bilibili.com",
            },
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    async def close(self):
        await self.client.aclose()

    # ── Step 1: Preupload ──

    async def _preupload(self, filepath: str) -> dict:
        """Get upload authorization."""
        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)
        params = {
            "name": filename,
            "size": str(filesize),
            "r": "upos",
            "profile": "ugcupos/bup",
            "ssl": "0",
            "version": "2.8.9",
            "build": "2081200",
        }
        resp = await self.client.get(self.PREUPLOAD_URL, params=params)
        data = resp.json()
        logger.info("Preupload response: OK, biz_id=%s", data.get("biz_id"))
        return data

    # ── Step 2-4: Upload file ──

    async def _upload_file(self, filepath: str, pre: dict) -> dict:
        """Init multipart → upload chunks → complete. Returns {filename, cid}."""
        upos_uri = pre["upos_uri"].replace("upos://", "")
        endpoint = pre["endpoint"]
        upload_url = f"https:{endpoint}/{upos_uri}"
        auth = pre["auth"]
        chunk_size = pre["chunk_size"]
        biz_id = pre["biz_id"]
        filesize = os.path.getsize(filepath)
        headers = {"x-upos-auth": auth, "Referer": "https://www.bilibili.com"}

        # Init multipart
        init_params = {
            "uploads": "",
            "output": "json",
            "profile": "ugcfx/bup",
            "filesize": str(filesize),
            "partsize": str(chunk_size),
            "biz_id": str(biz_id),
        }
        resp = await self.client.post(upload_url, params=init_params, headers=headers)
        init_data = resp.json()
        upload_id = init_data["upload_id"]

        # Upload chunks
        total_chunks = (filesize + chunk_size - 1) // chunk_size
        parts = []
        offset = 0
        chunk_number = 0

        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break

                real_size = len(chunk)
                chunk_params = {
                    "partNumber": str(chunk_number + 1),
                    "uploadId": upload_id,
                    "chunk": str(chunk_number),
                    "chunks": str(total_chunks),
                    "size": str(real_size),
                    "start": str(offset),
                    "end": str(offset + real_size),
                }
                chunk_resp = await self.client.put(
                    upload_url, content=chunk, params=chunk_params, headers=headers,
                )
                etag = chunk_resp.headers.get("Etag", "").strip('"')
                parts.append({"Part": {"PartNumber": chunk_number + 1, "ETag": etag}})
                chunk_number += 1
                offset += real_size

                if chunk_number % 5 == 0:
                    logger.info("Upload progress: %d/%d chunks", chunk_number, total_chunks)

        # Complete multipart
        parts.sort(key=lambda x: x["Part"]["PartNumber"])
        root = ET.Element("CompleteMultipartUpload")
        for p in parts:
            pe = ET.SubElement(root, "Part")
            ET.SubElement(pe, "PartNumber").text = str(p["Part"]["PartNumber"])
            ET.SubElement(pe, "ETag").text = p["Part"]["ETag"]
        xml_body = ET.tostring(root, encoding="unicode")

        complete_params = {
            "output": "json",
            "name": os.path.basename(filepath),
            "profile": "ugcfx/bup",
            "uploadId": upload_id,
            "biz_id": str(biz_id),
        }
        complete_headers = {**headers, "Content-Type": "application/json"}
        await self.client.post(
            upload_url, params=complete_params, content=xml_body, headers=complete_headers,
        )

        return {"filename": upos_uri, "cid": biz_id}

    # ── Step 5: Upload cover ──

    async def _upload_cover(self, image_path: str) -> str:
        """Upload cover image, returns cover URL."""
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        data = {
            "cover": f"data:image/jpeg;base64,{b64}",
            "csrf": self.cred.bili_jct,
        }
        resp = await self.client.post(self.COVER_UPLOAD_URL, data=data)
        result = resp.json()
        if result.get("code") == 0:
            return result["data"]["url"]
        logger.warning("Cover upload failed: %s", result.get("message"))
        return ""

    # ── Step 6: Submit ──

    async def submit(
        self,
        filepath: str,
        title: str,
        desc: str,
        tags: list[str],
        tid: int = 122,
        copyright_type: int = 2,
        source: str = "",
        cover_path: str = "",
        dynamic: str = "",
    ) -> BiliUploadResult:
        """Full upload flow + submit.

        Args:
            filepath: Path to video file.
            title: Video title (max 80 chars).
            desc: Video description.
            tags: List of tag strings.
            tid: Category ID (default 122 = 野生技术协会).
            copyright_type: 1=original, 2=repost.
            source: Source URL (required if copyright=2).
            cover_path: Optional cover image path.
            dynamic: Extra text for dynamic post.

        Returns:
            BiliUploadResult with bvid/aid on success.
        """
        try:
            # 1. Preupload
            pre = await self._preupload(filepath)

            # 2-4. Upload file (init + chunks + complete)
            video_info = await self._upload_file(filepath, pre)

            # 5. Cover (optional)
            cover_url = ""
            if cover_path and os.path.exists(cover_path):
                cover_url = await self._upload_cover(cover_path)

            # 6. Submit
            post_data = {
                "copyright": copyright_type,
                "videos": [{
                    "filename": video_info["filename"],
                    "title": title[:80],
                    "desc": desc,
                    "cid": video_info["cid"],
                }],
                "source": source,
                "tid": tid,
                "title": title[:80],
                "tag": ",".join(tags[:12]),  # max ~12 tags
                "desc_format_id": 0,
                "desc": desc,
                "cover": cover_url,
                "dynamic": dynamic,
                "subtitle": {"open": 0, "lan": ""},
                "dolby": 0,
                "lossless_music": 0,
                "no_reprint": 0,
                "open_elec": 0,
                "up_selection_reply": False,
                "up_close_reply": False,
                "up_close_danmu": False,
                "web_os": 3,
                "csrf": self.cred.bili_jct,
            }

            submit_resp = await self.client.post(
                f"{self.SUBMIT_URL}?csrf={self.cred.bili_jct}",
                json=post_data,
            )
            result = submit_resp.json()

            if result.get("code") == 0:
                data = result.get("data", {})
                return BiliUploadResult(
                    bvid=data.get("bvid", ""),
                    aid=data.get("aid", 0),
                    success=True,
                )
            else:
                return BiliUploadResult(
                    success=False,
                    error=f"Submit error {result.get('code')}: {result.get('message', '')}",
                )

        except Exception as e:
            logger.exception("Bilibili upload failed")
            return BiliUploadResult(success=False, error=str(e))


# ── Xigua Uploader (Playwright-based) ──


@dataclass
class XiguaUploadResult:
    """Result of a Xigua upload."""
    item_id: str = ""
    success: bool = False
    error: str = ""


class XiguaUploader:
    """Upload videos to Xigua/Toutiao via Playwright browser automation.

    Xigua does not have a public HTTP upload API for long-form videos.
    The creator platform uses ByteDance's internal VOD infrastructure with
    AWS-S3-style signatures. All major open-source projects use browser
    automation (Playwright/Selenium) for Xigua upload.

    Requires:
        pip install playwright
        playwright install chromium
    """

    UPLOAD_URL = (
        "https://mp.toutiao.com/profile_v4/xigua/upload-video?from=toutiao_pc"
    )

    def __init__(self, cookie_dict: dict):
        """Initialize with cookie dict from browser export.

        Args:
            cookie_dict: Dict with keys like name/domain/path/value for
                         ByteDance SSO cookies (sessionid, sid_tt, uid_tt, etc.)
        """
        self.cookies = cookie_dict

    async def upload(
        self,
        filepath: str,
        title: str,
        desc: str,
        tags: list[str],
        cover_path: str = "",
        publish_now: bool = True,
    ) -> XiguaUploadResult:
        """Upload video using Playwright browser automation.

        This is a blocking call (runs browser sync) — should be run in
        a thread pool executor or subprocess to avoid blocking the event loop.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return XiguaUploadResult(
                success=False,
                error="Playwright not installed. Run: pip install playwright && playwright install chromium",
            )

        result = XiguaUploadResult()

        def _run():
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                )

                # Inject cookies
                context.add_cookies([self.cookies])

                page = context.new_page()
                page.goto(self.UPLOAD_URL, wait_until="networkidle")

                # 1. Upload video file via file input
                file_input = page.locator("input[type=file]")
                file_input.set_input_files(filepath)

                # 2. Wait for upload to finish (progress bar disappears)
                page.wait_for_timeout(3000)
                # Wait up to 10min for upload
                page.wait_for_function(
                    "() => document.querySelector('.upload-success, .byte-upload-status--done') !== null",
                    timeout=600000,
                )

                # 3. Fill title
                title_input = page.locator("input[placeholder*='标题'], input[class*='title']")
                if title_input.is_visible():
                    title_input.fill(title[:30])

                # 4. Fill description
                desc_textarea = page.locator("textarea")
                if desc_textarea.is_visible():
                    tag_text = " ".join(f"#{t}" for t in tags)
                    full_desc = f"{desc}\n{tag_text}" if tag_text else desc
                    desc_textarea.fill(full_desc[:2000])

                # 5. Optional cover
                if cover_path and os.path.exists(cover_path):
                    cover_input = page.locator("input[accept*='image']")
                    if cover_input.is_visible():
                        cover_input.set_input_files(cover_path)

                # 6. Publish
                if publish_now:
                    publish_btn = page.locator("button:has-text('发布'), button:has-text('发表')")
                    if publish_btn.is_visible():
                        publish_btn.click()
                        page.wait_for_timeout(5000)

                # Store result
                current_url = page.url
                result.item_id = current_url  # fallback: URL contains item info
                browser.close()

        # Run in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _run)

        result.success = True
        return result
