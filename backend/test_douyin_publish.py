"""Douyin publish test — login + video upload via social-auto-upload.

Usage: cd backend && python test_douyin_publish.py
"""
import asyncio
import os
import sys
from pathlib import Path

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
SAU_DIR = os.path.normpath(os.path.join(BACKEND_DIR, "..", "social-auto-upload"))

# ── Step 0: Find video from DB while still in backend dir ──
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

from sqlalchemy import select
from app.core.database import async_session_factory
from app.models.video import Video


async def find_video():
    """Find a dubbed video to upload."""
    async with async_session_factory() as session:
        vids = (await session.execute(
            select(Video).where(Video.dubbed_filepath.isnot(None)).order_by(Video.id)
        )).scalars().all()
    for v in vids:
        path = os.path.abspath(v.dubbed_filepath)
        if os.path.exists(path):
            return v, path
    return None, None


async def main():
    v, video_path = await find_video()
    if not v:
        print("No dubbed videos available!")
        return 1

    print(f"Video: {v.title}")
    print(f"File: {video_path} ({os.path.getsize(video_path)} bytes)")

    # ── Step 1: Switch to SAU for login/upload ──
    os.chdir(SAU_DIR)
    sys.path.insert(0, SAU_DIR)

    import conf
    conf.LOCAL_CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    conf.LOCAL_CHROME_HEADLESS = False
    conf.DEBUG_MODE = True
    os.makedirs(os.path.join(SAU_DIR, "cookies"), exist_ok=True)

    from uploader.douyin_uploader.main import DouYinVideo, douyin_setup
    from utils.log import douyin_logger

    account_file = os.path.join(SAU_DIR, "cookies", "douyin_you2bili.json")

    # Login
    douyin_logger.info("=" * 60)
    douyin_logger.info("Douyin login / cookie check")
    douyin_logger.info("=" * 60)
    douyin_logger.info("If not logged in, scan QR code with 抖音 App")

    result = await douyin_setup(
        account_file, handle=True, return_detail=True, headless=False,
    )
    if not result.get("success"):
        print(f"Login failed: {result.get('message')}")
        return 1

    print(f"Login OK: {result['status']}")

    # Upload
    print("\n" + "=" * 60)
    print("Uploading video to Douyin...")
    print("=" * 60)

    uploader = DouYinVideo(
        title=v.title[:80],
        file_path=video_path,
        tags=["科技", "AI", "搬运"],
        desc=v.title[:80],
        publish_date=0,
        account_file=account_file,
        headless=False,
    )

    try:
        await uploader.douyin_upload_video()
        print("\nSUCCESS: Video uploaded to Douyin!")
        return 0
    except Exception as e:
        print(f"\nFAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        os.chdir(BACKEND_DIR)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    sys.exit(asyncio.run(main()))
