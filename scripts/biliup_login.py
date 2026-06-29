"""Bilibili QR code login — generates a biliup-compatible cookie file.

Usage: python biliup_login.py
1. Displays a QR code image for you to scan with the Bilibili app
2. Polls for login confirmation
3. Saves cookies in biliup LoginInfo format to social-auto-upload/cookies/
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import httpx
import qrcode

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# ── Constants ──
GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
CORRESPOND_URL = "https://passport.bilibili.com/x/passport-login/web/login/correspond/1"
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"

QR_TIMEOUT = 180  # 3 minutes
POLL_INTERVAL = 2  # seconds

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "social-auto-upload" / "cookies"
OUTPUT_FILE = OUTPUT_DIR / "bilibili_viddub.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}


async def generate_qr(client: httpx.AsyncClient) -> dict:
    """Step 1: Get QR code URL and key."""
    resp = await client.get(GENERATE_URL)
    data = resp.json()
    if data["code"] != 0:
        raise RuntimeError(f"QR generate failed: {data}")
    return data["data"]  # {url, qrcode_key}


def save_qr_image(qr_url: str, path: str) -> None:
    """Generate QR code PNG from URL text."""
    img = qrcode.make(qr_url)
    img.save(path)
    print(f"\nQR code saved to: {path}")
    print(f"Open this file and scan with Bilibili app")
    print(f"QR content: {qr_url}")


async def poll_login(
    client: httpx.AsyncClient, qrcode_key: str, timeout: int = QR_TIMEOUT
) -> dict:
    """Step 2: Poll until user scans and confirms."""
    deadline = time.time() + timeout
    last_status = None
    while time.time() < deadline:
        resp = await client.get(POLL_URL, params={"qrcode_key": qrcode_key})
        data = resp.json()
        if data["code"] != 0:
            await asyncio.sleep(POLL_INTERVAL)
            continue

        status = data["data"]
        code = status.get("code", -1)

        if code != last_status:
            status_msgs = {
                0: "Login confirmed!",
                86038: "QR expired",
                86090: "Scanned — waiting for confirmation...",
                86101: "Waiting for scan...",
            }
            print(f"  [{code}] {status_msgs.get(code, f'Unknown status: {code}')}")
            last_status = code

        if code == 0:  # success
            return status
        elif code == 86038:  # expired
            raise RuntimeError("QR code expired")

        await asyncio.sleep(POLL_INTERVAL)

    raise TimeoutError("Login timed out")


async def exchange_token(
    client: httpx.AsyncClient, refresh_token: str
) -> dict[str, str]:
    """Step 3: Exchange refresh_token for session cookies via correspond/1."""
    resp = await client.get(f"{CORRESPOND_URL}/{refresh_token}")
    cookies: dict[str, str] = {}
    for cookie in client.cookies.jar:
        if cookie.domain and "bilibili" in cookie.domain:
            cookies[cookie.name] = cookie.value
    print(f"  Exchanged refresh_token → {len(cookies)} cookies: {list(cookies.keys())}")
    return cookies


async def fetch_user_info(client: httpx.AsyncClient) -> dict:
    """Step 4: Get user info from nav API."""
    resp = await client.get(NAV_URL)
    data = resp.json()
    if data["code"] == 0:
        return data["data"]
    return {}


def save_biliup_cookies(cookies: dict[str, str], user_info: dict) -> str:
    """Save cookies in biliup LoginInfo format."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    mid_str = cookies.get("DedeUserID", "0")
    try:
        mid = int(mid_str)
    except (ValueError, TypeError):
        mid = 0

    login_info = {
        "cookie_info": {k: v for k, v in cookies.items()},
        "sso": [],
        "token_info": {
            "mid": mid,
            "access_token": cookies.get("access_token", ""),
            "refresh_token": cookies.get("refresh_token", ""),
            "expires_in": 0,
        },
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(login_info, f, ensure_ascii=False, indent=2)

    print(f"\nCookies saved to: {OUTPUT_FILE}")
    print(f"  mid: {mid}")
    print(f"  cookies: {list(cookies.keys())}")
    print(f"  access_token: {'present' if login_info['token_info']['access_token'] else 'absent'}")
    return str(OUTPUT_FILE)


async def main():
    print("=" * 60)
    print("Bilibili QR Code Login → biliup cookie format")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True) as client:
        # Step 1: Generate QR code
        print("\n[1/4] Generating QR code...")
        qr_data = await generate_qr(client)
        qr_url = qr_data["url"]
        qrcode_key = qr_data["qrcode_key"]

        qr_path = os.path.join(os.path.dirname(__file__), "bilibili_qr.png")
        save_qr_image(qr_url, qr_path)

        # Step 2: Poll for login
        print(f"\n[2/4] Waiting for scan (timeout: {QR_TIMEOUT}s)...")
        try:
            login_data = await poll_login(client, qrcode_key)
        except (RuntimeError, TimeoutError) as e:
            print(f"\nLogin failed: {e}")
            return 1

        # Step 3: Exchange tokens + get all cookies
        print("\n[3/4] Exchanging tokens...")
        all_cookies: dict[str, str] = {}

        # Get cookies from the poll response
        jar_cookies: dict[str, str] = {}
        for cookie in client.cookies.jar:
            if cookie.domain and "bilibili" in cookie.domain:
                jar_cookies[cookie.name] = cookie.value
        print(f"  Jar cookies: {list(jar_cookies.keys())}")

        all_cookies.update(jar_cookies)

        # Exchange refresh_token if available
        refresh_token = login_data.get("refresh_token", "")
        if refresh_token:
            token_cookies = await exchange_token(client, refresh_token)
            all_cookies.update(token_cookies)
        else:
            print("  No refresh_token in response, using jar cookies only")

        if not all_cookies:
            print("ERROR: No cookies obtained!")
            return 1

        # Step 4: Get user info
        print("\n[4/4] Fetching user info...")
        user_info = await fetch_user_info(client)

        if user_info:
            print(f"  User: {user_info.get('uname', 'unknown')} (uid: {user_info.get('mid', '?')})")
            print(f"  Level: {user_info.get('level_info', {}).get('current_level', '?')}")

        # Save in biliup format
        cookie_path = save_biliup_cookies(all_cookies, user_info)

        # Verify with biliup
        print("\n" + "=" * 60)
        print("Test: biliup renew")
        import subprocess

        biliup_bin = os.path.expanduser(
            r"~\.social-auto-upload\tools\biliup\windows-x86_64\biliup.exe"
        )
        result = subprocess.run(
            [biliup_bin, "-u", str(OUTPUT_FILE), "renew"],
            capture_output=True, text=True, timeout=30,
        )
        print(f"  rc={result.returncode}")
        if result.returncode == 0:
            print("  renew OK")

            # Test list
            print("\nTest: biliup list")
            result2 = subprocess.run(
                [biliup_bin, "-u", str(OUTPUT_FILE), "list"],
                capture_output=True, text=True, timeout=30,
            )
            print(f"  rc={result2.returncode}")
            if result2.stdout:
                print(f"  stdout: {result2.stdout[:500]}")
            if result2.stderr:
                print(f"  stderr: {result2.stderr[:500]}")
        else:
            if result.stderr:
                print(f"  stderr: {result.stderr[:300]}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
