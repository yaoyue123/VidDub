"""Bilibili publisher using social-auto-upload (biliup Rust binary).

Replaces the old python -m biliup and Playwright-based publishers.

Uses social-auto-upload's biliup binary management (ensure_biliup_binary)
and run_biliup_command for Rust CLI-based upload:
- Auto-downloads/manages biliup binary from GitHub releases
- No browser automation required
- Built-in retry, resume, and metadata support

Cookie format: converts viddub's storage_state to biliup's LoginInfo JSON
via cookie_bridge.py (same format used by social-auto-upload).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Optional

from app.services.publish.base import (
    PlatformPublisher,
    PublishFields,
    PublishResult,
    UPLOAD_TIMEOUT_SEC,
)
from app.services.publish.cookie_bridge import (
    convert_storage_state_to_biliup,
)

logger = logging.getLogger(__name__)

# ── Add social-auto-upload to Python path ──
_SAU_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "social-auto-upload")
)
if os.path.isdir(_SAU_DIR) and _SAU_DIR not in sys.path:
    sys.path.insert(0, _SAU_DIR)
    logger.info("Added social-auto-upload to sys.path: %s", _SAU_DIR)

# Default tid: 122 = 野生技术协会
DEFAULT_TID = "122"

# Default tags (fallback when none provided)
DEFAULT_TAGS = ["搬运"]

# Regex to extract BV number from biliup output
BV_PATTERN = re.compile(r'(BV[0-9A-Za-z]{10,})')

# biliup CLI timeout per call
RENEW_TIMEOUT_SEC = 60


class SauBilibiliPublisher(PlatformPublisher):
    """Bilibili publisher that uses social-auto-upload's biliup Rust binary.

    Usage flow:
        1. Cookie: convert storage_state -> biliup LoginInfo JSON
        2. Upload: biliup -u <cookie> upload <video> --title T --desc D --tid N --tag TAGS
        3. Validate: biliup -u <cookie> renew

    Delegates binary management to social-auto-upload's
    uploader.bilibili_uploader.runtime module (ensure_biliup_binary).
    """

    platform = "bilibili"

    def __init__(
        self,
        storage_state_path: str,
        upload_timeout: int = UPLOAD_TIMEOUT_SEC,
    ) -> None:
        self.storage_state_path = storage_state_path
        self.upload_timeout = upload_timeout
        self._biliup_binary: Optional[str] = None

    # ── PlatformPublisher interface ──

    async def validate_login(self) -> bool:
        """Check if the Bilibili cookies are still valid.

        Uses social-auto-upload's ensure_biliup_binary + biliup renew.
        """
        storage_state = self._load_storage_state()
        if storage_state is None:
            logger.warning("validate_login: storage_state missing for bilibili")
            return False

        cookie_file = None
        try:
            cookie_file = self._create_cookie_file(storage_state)
            binary = await self._get_biliup_binary()
            proc = await asyncio.create_subprocess_exec(
                binary, "-u", cookie_file, "renew",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=RENEW_TIMEOUT_SEC
                )
            except asyncio.TimeoutError:
                proc.kill()
                logger.warning("biliup renew timed out")
                return False

            if proc.returncode == 0:
                return True

            stderr_text = stderr.decode("utf-8", errors="replace")
            logger.debug("biliup renew failed: rc=%d, stderr=%s",
                         proc.returncode, stderr_text[:200])
            return False

        except ImportError as e:
            logger.warning("social-auto-upload import error: %s", e)
            return False
        except Exception as e:
            logger.warning("validate_login exception: %s", e)
            return False
        finally:
            self._cleanup_cookie(cookie_file)

    async def publish(
        self,
        video_id: int,
        fields: PublishFields,
        video_file_path: str,
        progress_callback: Optional[Any] = None,
    ) -> PublishResult:
        """Publish video to Bilibili via social-auto-upload's biliup binary.

        Delegates to run_biliup_command from social-auto-upload's runtime.
        """
        if not os.path.exists(video_file_path):
            return PublishResult(
                success=False,
                error_msg=f"视频文件不存在: {video_file_path}",
            )

        # 1. Load cookies
        storage_state = self._load_storage_state()
        if storage_state is None:
            return PublishResult(
                success=False,
                error_msg="未登录哔哩哔哩 (storage_state 缺失)",
                needs_relogin=True,
            )

        cookie_file = None
        try:
            cookie_file = self._create_cookie_file(storage_state)
        except ValueError as e:
            return PublishResult(
                success=False,
                error_msg=str(e),
                needs_relogin=True,
            )
        except Exception as e:
            logger.error("Failed to create biliup cookie: %s", e)
            return PublishResult(
                success=False,
                error_msg=f"cookie 转换失败: {e}",
            )

        # 2. Build command (social-auto-upload format)
        tid = fields.category_id or DEFAULT_TID
        tags = list(fields.tags) if fields.tags else list(DEFAULT_TAGS)
        title = self._safe_text(fields.title, 80)
        # Bilibili API rejects newlines / special chars in description
        import re as _re
        raw_desc = self._safe_text(fields.description or title, 2000)
        desc = _re.sub(r'[\r\n]+', ' ', raw_desc)  # replace newlines with space
        desc = _re.sub(r'[^\x20-\x7E\u4e00-\u9fff\u3000-\u303f\uff00-\uffef,.;:!?，。；：！？、\s]', '', desc)
        desc = desc[:2000].strip()

        args = [
            "-u", cookie_file,
            "upload", video_file_path,
            "--title", title,
            "--desc", desc,
            "--tid", str(tid),
            "--tag", ",".join(tags),
            "--copyright", "2",  # 2 = repost
        ]

        logger.info(
            "Bilibili publish via biliup binary: --title %s --tid %s --tags %s",
            title[:40], tid, len(tags),
        )

        # 3. Execute with progress
        await self._report_progress(progress_callback, "preparing", 5)

        try:
            result = await self._run_sau_command(args)

            # 4. Parse result
            if result.returncode == 0:
                bv_url = self._extract_bv_url(
                    result.stdout, result.stderr, video_id
                )
                await self._report_progress(progress_callback, "completed", 100)
                logger.info(
                    "Bilibili publish success for video %d: %s",
                    video_id, bv_url or "BV not found in output",
                )
                return PublishResult(
                    success=True,
                    platform_video_url=bv_url,
                )
            else:
                error_msg = self._extract_error(
                    result.stdout, result.stderr
                )
                logger.error(
                    "Bilibili publish failed for video %d: %s",
                    video_id, error_msg,
                )
                needs_relogin = self._detect_relogin_needed(error_msg)
                return PublishResult(
                    success=False,
                    error_msg=f"B站上传失败: {error_msg}",
                    needs_relogin=needs_relogin,
                )

        except asyncio.TimeoutError:
            logger.error("Bilibili upload timed out after %ds for video %d",
                         self.upload_timeout, video_id)
            return PublishResult(
                success=False,
                error_msg=f"上传超时 ({self.upload_timeout}s)",
            )
        except Exception as e:
            logger.error("Bilibili publish crashed: %s", e, exc_info=True)
            return PublishResult(
                success=False,
                error_msg=str(e),
            )
        finally:
            self._cleanup_cookie(cookie_file)

    # ── Internal helpers ──

    async def _get_biliup_binary(self) -> str:
        """Get path to biliup Rust binary via social-auto-upload.

        Delegates to ensure_biliup_binary for auto-download/management.
        Caches the binary path after first call.
        """
        if self._biliup_binary:
            return self._biliup_binary

        # Import from social-auto-upload's runtime module
        try:
            from uploader.bilibili_uploader.runtime import ensure_biliup_binary as _ensure
        except ImportError as err:
            raise ImportError(
                f"social-auto-upload not found at {_SAU_DIR}. "
                f"Clone it alongside the backend directory. "
                f"Original error: {err}"
            ) from err

        # run in thread to avoid blocking event loop (ensure_biliup_binary does HTTP requests)
        binary_path = await asyncio.to_thread(_ensure, False)
        self._biliup_binary = str(binary_path)
        logger.info("Using biliup binary: %s", self._biliup_binary)
        return self._biliup_binary

    async def _run_sau_command(
        self, args: list[str],
    ) -> subprocess.CompletedProcess:
        """Run biliup command using social-auto-upload's binary management.

        Uses asyncio.create_subprocess_exec to avoid blocking the event loop
        (social-auto-upload's run_biliup_command is synchronous).
        """
        binary = await self._get_biliup_binary()
        cmd = [binary] + args
        logger.debug("Running biliup: %s ...%s",
                     os.path.basename(binary), " ".join(args[:4]))

        proc = await asyncio.create_subprocess_exec(
            binary, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self.upload_timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise

        stdout_str = stdout_bytes.decode("utf-8", errors="replace")
        stderr_str = stderr_bytes.decode("utf-8", errors="replace")

        return subprocess.CompletedProcess(
            cmd, proc.returncode or 0,
            stdout=stdout_str,
            stderr=stderr_str,
        )

    def _load_storage_state(self) -> Optional[dict]:
        """Load storage_state JSON from the configured path."""
        if not os.path.exists(self.storage_state_path):
            return None
        try:
            import json
            with open(self.storage_state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError) as e:
            logger.warning("Failed to load storage_state: %s", e)
            return None

    def _create_cookie_file(self, storage_state: dict) -> str:
        """Create a temp biliup cookie file and return its path."""
        fd, path = tempfile.mkstemp(suffix="_biliup_cookies.json", prefix="bili_")
        os.close(fd)
        convert_storage_state_to_biliup(storage_state, path)
        return path

    def _cleanup_cookie(self, cookie_path: Optional[str]) -> None:
        """Remove temp cookie file."""
        if cookie_path and os.path.exists(cookie_path):
            try:
                os.unlink(cookie_path)
            except OSError as e:
                logger.debug("Failed to remove temp cookie %s: %s", cookie_path, e)

    def _extract_bv_url(
        self, stdout: str, stderr: str, video_id: int
    ) -> Optional[str]:
        """Try to extract the published BV URL from biliup output."""
        combined = stdout + "\n" + stderr

        # Look for BV number pattern
        match = BV_PATTERN.search(combined)
        if match:
            bv = match.group(1)
            return f"https://www.bilibili.com/video/{bv}"

        # Fallback: log the output for debugging
        logger.debug(
            "No BV found in biliup output for video %d. "
            "stdout(%.200s) stderr(%.200s)",
            video_id, stdout, stderr,
        )
        return None

    def _extract_error(self, stdout: str, stderr: str) -> str:
        """Extract meaningful error message from biliup output."""
        combined = (stderr or "") + "\n" + (stdout or "")

        # Look for specific error patterns
        patterns = [
            (r'╰─▶ (.+)', 1),           # error_stack error message
            (r'error: (.+)', 1),        # generic error
            (r'Unknown Error', 0),      # fallback
        ]

        for pat, group in patterns:
            m = re.search(pat, combined, re.DOTALL)
            if m:
                msg = m.group(group).strip() if group else pat
                if msg:
                    return msg[:200]

        # Last resort: return the first non-empty line of stderr
        for line in stderr.split("\n"):
            clean = line.strip()
            if clean and "INFO" not in clean and "Tracing" not in clean:
                return clean[:200]

        return "biliup 上传失败（未知错误）"

    def _detect_relogin_needed(self, error_msg: str) -> bool:
        """Detect if error indicates cookie/session expired."""
        relogin_keywords = [
            "expired", "login", "token", "credential",
            "未登录", "登录过期", "cookie", "permission denied",
        ]
        msg_lower = error_msg.lower()
        return any(kw in msg_lower for kw in relogin_keywords)

    @staticmethod
    async def _report_progress(
        callback: Optional[Any], stage: str, pct: float,
    ) -> None:
        if callback:
            try:
                await callback(stage, pct)
            except Exception:
                pass
