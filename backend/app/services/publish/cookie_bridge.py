"""Cookie bridge: convert viddub storage_state -> biliup LoginInfo format.

biliup (Rust CLI / social-auto-upload) expects a cookie file with this LoginInfo JSON structure:
{
    "cookie_info": { <cookie_name>: <cookie_value>, ... },
    "sso": [],
    "token_info": {
        "mid": <int>,
        "access_token": "...",
        "refresh_token": "...",
        "expires_in": <unix_timestamp>
    }
}

The source storage_state comes from Phase 6 LoginManager, in one of two formats:
- Dict format:  {"cookies": {"name": "value", ...}, "user_info": {...}}
- List format:  {"cookies": [{"name": "n", "value": "v", ...}], "origins": [...]}

social-auto-upload stores cookies at: {project_root}/cookies/bilibili_{account_name}.json
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

# Cookies required for bilibili API auth
BILI_REQUIRED_COOKIES = frozenset({
    "SESSDATA",
    "bili_jct",
    "DedeUserID",
    "buvid3",
    "buvid4",
    "sid",
})

# Relative path from project root to social-auto-upload cookies directory
SAU_COOKIES_DIR = "social-auto-upload/cookies"


def convert_storage_state_to_biliup(
    storage_state: dict,
    cookie_file_path: str,
) -> str:
    """Convert viddub storage_state dict to biliup LoginInfo JSON file.

    Returns the cookie_file_path on success.
    Raises ValueError if critical cookies are missing.
    """
    cookies_flat = _extract_cookie_dict(storage_state)
    user_info = storage_state.get("user_info") or {}

    # Ensure minimum required cookies for bilibili
    has_sessdata = "SESSDATA" in cookies_flat
    has_bili_jct = "bili_jct" in cookies_flat

    if not has_sessdata or not has_bili_jct:
        logger.warning(
            "Missing critical bilibili cookies: SESSDATA=%s, bili_jct=%s",
            has_sessdata, has_bili_jct,
        )
        missing = []
        if not has_sessdata:
            missing.append("SESSDATA")
        if not has_bili_jct:
            missing.append("bili_jct")
        raise ValueError(f"缺少哔哩哔哩登录必要 cookie: {', '.join(missing)}；请重新登录")

    # Build token_info from storage_state or use placeholders
    mid = cookies_flat.get("DedeUserID")
    try:
        mid_int = int(mid) if mid else 0
    except (ValueError, TypeError):
        mid_int = 0

    # access_token / refresh_token may be in storage_state or token_info
    token_info = storage_state.get("token_info") or user_info.get("token_info") or {}
    access_token = token_info.get("access_token") or cookies_flat.get("access_token", "")
    refresh_token = token_info.get("refresh_token") or cookies_flat.get("refresh_token", "")
    expires_in = token_info.get("expires_in", 0)
    if isinstance(expires_in, str):
        try:
            expires_in = int(expires_in)
        except (ValueError, TypeError):
            expires_in = 0

    login_info = {
        "cookie_info": cookies_flat,
        "sso": [],
        "token_info": {
            "mid": mid_int,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
        },
    }

    # Write atomically
    tmp_path = cookie_file_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(login_info, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, cookie_file_path)

    logger.debug(
        "Wrote biliup cookie file with %d cookies (mid=%s)",
        len(cookies_flat), mid,
    )
    return cookie_file_path


def _extract_cookie_dict(storage_state: dict) -> dict[str, str]:
    """Extract a flat {name: value} dict of cookies from storage_state.

    Handles both:
    - Dict format: {"cookies": {"name": "value", ...}}
    - List format: {"cookies": [{"name": "n", "value": "v", ...}, ...]}
    """
    cookies_raw = storage_state.get("cookies", {})

    if isinstance(cookies_raw, dict):
        # Dict format from Phase 6
        return {str(k): str(v) for k, v in cookies_raw.items() if v is not None}

    elif isinstance(cookies_raw, list):
        # Playwright standard format
        result = {}
        for c in cookies_raw:
            name = c.get("name")
            value = c.get("value")
            if name and value is not None:
                result[str(name)] = str(value)
        return result

    else:
        logger.warning("Unexpected cookies type: %s", type(cookies_raw).__name__)
        return {}


def create_temp_cookie_file(storage_state: dict) -> str:
    """Create a temp biliup cookie file and return its path.
    Caller must delete the file when done.
    """
    fd, path = tempfile.mkstemp(suffix="_biliup_cookies.json", prefix="bili_")
    os.close(fd)
    return convert_storage_state_to_biliup(storage_state, path)


# ── social-auto-upload cookie directory integration ──

def _find_project_root() -> Optional[str]:
    """Walk up from this file to find the project root (where social-auto-upload/ lives)."""
    current = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):  # max 6 levels up
        if os.path.isdir(os.path.join(current, "social-auto-upload")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def get_sau_cookies_dir() -> Optional[str]:
    """Return social-auto-upload's cookies directory path, or None if not found."""
    root = _find_project_root()
    if root is None:
        return None
    cookies_dir = os.path.join(root, SAU_COOKIES_DIR)
    os.makedirs(cookies_dir, exist_ok=True)
    return cookies_dir


def write_sau_bilibili_cookie(
    storage_state: dict,
    account_name: str = "viddub",
) -> Optional[str]:
    """Write a social-auto-upload compatible bilibili cookie file.

    Writes to: {project_root}/social-auto-upload/cookies/bilibili_{account_name}.json

    This enables direct use with social-auto-upload's CLI:
        sau bilibili check --account viddub
        sau bilibili upload-video --account viddub --file video.mp4 --title T --tid N

    Args:
        storage_state: viddub storage_state dict
        account_name: account identifier (default: "viddub")

    Returns:
        Path to the written cookie file, or None on failure.
    """
    cookies_dir = get_sau_cookies_dir()
    if cookies_dir is None:
        logger.warning("Cannot find project root for social-auto-upload cookies")
        return None

    cookie_path = os.path.join(cookies_dir, f"bilibili_{account_name}.json")

    try:
        convert_storage_state_to_biliup(storage_state, cookie_path)
        logger.info("Wrote social-auto-upload bilibili cookie: %s", cookie_path)
        return cookie_path
    except ValueError as e:
        logger.warning("Failed to write social-auto-upload cookie: %s", e)
        return None
    except Exception as e:
        logger.warning("Error writing social-auto-upload cookie: %s", e)
        return None


def sync_storage_state_to_sau(
    platform: str,
    account_name: str = "viddub",
) -> Optional[str]:
    """Sync a platform's storage_state to social-auto-upload's cookie directory.

    Loads the storage_state from viddub's login manager and writes
    it in social-auto-upload's expected cookie format.

    Currently supports: 'bilibili'

    Args:
        platform: Platform name ('bilibili')
        account_name: social-auto-upload account identifier

    Returns:
        Path to the written cookie file, or None on failure.
    """
    if platform not in ("bilibili",):
        logger.warning("sync_storage_state_to_sau: unsupported platform '%s'", platform)
        return None

    from app.services.platform.manager import get_login_manager
    lm = get_login_manager()
    storage_state = lm.load_storage_state(platform)
    if storage_state is None:
        logger.warning("sync_storage_state_to_sau: no storage_state for %s", platform)
        return None

    return write_sau_bilibili_cookie(storage_state, account_name)
