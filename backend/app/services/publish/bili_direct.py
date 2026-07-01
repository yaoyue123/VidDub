"""Direct Bilibili video upload via httpx (bypasses biliup binary)."""
import asyncio
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import re
import time
import uuid
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BILI_API = "https://api.bilibili.com"
BILI_MEMBER = "https://member.bilibili.com"
BILI_UPOS = "https://upos-sz-upcdn.bilivideo.com"

# WBI signing key cache
_wbi_key: Optional[dict] = None


async def _get_wbi_key(client: httpx.AsyncClient) -> dict:
    """Get WBI signing key from Bilibili API."""
    global _wbi_key
    if _wbi_key:
        return _wbi_key
    r = await client.get(f"{BILI_API}/x/web-interface/nav")
    data = r.json().get("data", {})
    is_login = data.get("isLogin", False)
    if not is_login:
        raise RuntimeError("Not logged in to Bilibili")
    # The wbi_img URL contains the key
    wbi_img = data.get("wbi_img", {}) or {}
    img_url = wbi_img.get("img_url", "")
    sub_url = wbi_img.get("sub_url", "")
    if not img_url or not sub_url:
        raise RuntimeError("Cannot get WBI key - login may be expired")
    # Extract keys from URLs
    img_key = img_url.rsplit("/", 1)[-1].split(".")[0] if img_url else ""
    sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0] if sub_url else ""
    _wbi_key = {"img_key": img_key, "sub_key": sub_key}
    return _wbi_key


def _encrypt_wbi(params: dict, img_key: str, sub_key: str) -> dict:
    """Sign request parameters with WBI key."""
    mix_key = hashlib.md5((img_key + sub_key).encode()).hexdigest()
    sorted_params = sorted(params.items())
    query = "&".join(f"{k}={v}" for k, v in sorted_params)
    sign = hmac.new(mix_key.encode(), query.encode(), hashlib.md5).hexdigest()
    params["wts"] = int(time.time())
    params["w_rid"] = sign
    return params


def _build_headers(cookies: dict) -> dict:
    """Build standard Bilibili API headers."""
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.bilibili.com/",
    }


async def upload_bilibili(
    cookie_info: dict,
    video_path: str,
    title: str,
    desc: str = "",
    tid: int = 122,
    tags: list[str] = None,
    copyright_type: int = 1,
) -> dict:
    """Upload a video to Bilibili using direct HTTP API calls.

    Args:
        cookie_info: Dict with SESSDATA, bili_jct, DedeUserID, etc.
        video_path: Absolute path to video file.
        title: Video title.
        desc: Video description.
        tid: Category ID (default 122 = 野生技术协会).
        tags: List of tag strings.
        copyright_type: 1=original, 2=repost.

    Returns:
        Dict with success status and video URL or error.
    """
    cookies = {k: str(v) for k, v in cookie_info.items() if v}
    tags = tags or ["搬运"]
    headers = _build_headers(cookies)

    async with httpx.AsyncClient(cookies=cookies, headers=headers, timeout=120.0) as client:
        logger.info("Bilibili: verifying login...")
        nav = await client.get(f"{BILI_API}/x/web-interface/nav")
        nav_data = nav.json().get("data", {})
        if not nav_data.get("isLogin"):
            return {"success": False, "error": "Bilibili login expired, please re-login"}

        mid = nav_data.get("mid", 0)
        csrf = cookies.get("bili_jct", "")
        logger.info("Bilibili: logged in as mid=%s", mid)

        # Step 1: Preupload - get upload URL
        logger.info("Bilibili: preupload...")
        file_size = os.path.getsize(video_path)
        file_name = os.path.basename(video_path)
        ext = os.path.splitext(file_name)[1].lstrip(".") or "mp4"

        preupload_params = {
            "name": file_name,
            "size": str(file_size),
            "r": "upos",
            "profile": "ugcupos",
            "ssl": "0",
            "version": "2.8.10",
            "build": "2080100",
        }
        
        # Need WBI signed for preupload
        pre_r = await client.get(f"{BILI_API}/x/web-interface/nav", params={})
        
        # Direct preupload (some endpoints don't need WBI)
        pre_r = await client.post(
            f"{BILI_MEMBER}/x/web/archive/preupload",
            data=preupload_params,
        )
        pre_data = pre_r.json()
        logger.info("Preupload response: %s", json.dumps(pre_data, ensure_ascii=False)[:300])

        if pre_data.get("code") != 0:
            return {"success": False, "error": f"Preupload failed: {pre_data.get('message', 'unknown')}"}

        upos_uri = pre_data.get("upos_uri", "")
        endpoint = pre_data.get("endpoint", BILI_UPOS)
        upload_url = f"{endpoint}{upos_uri}"

        # Step 2: Upload the file
        logger.info("Bilibili: uploading video file...")
        mime_type, _ = mimetypes.guess_type(video_path) or ("video/mp4",)

        with open(video_path, "rb") as f:
            file_data = f.read()

        upload_r = await client.put(
            upload_url,
            content=file_data,
            headers={"Content-Type": mime_type},
        )
        logger.info("Upload response: %s", upload_r.status_code)

        if upload_r.status_code != 200:
            return {"success": False, "error": f"Upload failed with HTTP {upload_r.status_code}"}

        # Step 3: Submit the video
        logger.info("Bilibili: submitting video...")
        tag_str = ",".join(tags[:12])
        submit_data = {
            "copyright": copyright_type,
            "source": "",
            "tid": tid,
            "cover": "",
            "title": title[:80],
            "desc_format_id": "0",
            "desc": desc[:2000],
            "dynamic": "",
            "tag": tag_str,
            "videos": "[{\"filename\":\""
                     + upos_uri.split("/")[-1]
                     + "\",\"title\":\""
                     + title[:80]
                     + "\"}]",
            "no_reprint": "0",
            "open_elec": "0",
            "up_selection_reply": "0",
            "up_close_reply": "0",
            "up_close_danmu": "0",
            "dolby": "0",
            "lossless_music": "0",
            "charge": "0",
            "interactive": "0",
            "csrf": csrf,
        }

        submit_r = await client.post(
            f"{BILI_MEMBER}/x/v2/archive/add",
            data=submit_data,
        )
        submit_res = submit_r.json()
        logger.info("Submit response: %s", json.dumps(submit_res, ensure_ascii=False)[:500])

        if submit_res.get("code") == 0:
            data = submit_res.get("data", {})
            aid = data.get("aid")
            bv = data.get("bvid", "")
            return {
                "success": True,
                "aid": aid,
                "bvid": bv,
                "url": f"https://www.bilibili.com/video/{bv}" if bv else None,
            }
        else:
            return {
                "success": False,
                "error": f"Submit failed: {submit_res.get('message', 'unknown')}",
            }
