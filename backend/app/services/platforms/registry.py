"""Central platform registry — single source of truth for platform metadata.

Every platform that viddub can publish/login to is described here. The
PublishManager, LoginManager, and API routes all derive their platform lists,
display names, cookie paths, and dispatch from this module — eliminating the
previous if/elif chains scattered across the codebase.

A PlatformDescriptor bundles:
- Identity (id, display name, branding)
- Cookie file location (full path)
- Dispatch metadata (publisher/login module + class names, login kind)

Adding a new platform = adding one entry here. Removing one = deleting its
entry (plus its publisher/login modules).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


# ── Path helpers ──

# social-auto-upload/ lives at the project root (sibling of backend/)
_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
SAU_DIR = os.path.join(_PROJECT_ROOT, "social-auto-upload")
SAU_COOKIES_DIR = os.path.join(SAU_DIR, "cookies")

# viddub legacy storage_state directory (used only by transitional ixigua
# support which is scheduled for removal in P5)
VIDDUB_LOGIN_DATA_DIR = os.path.join(_PROJECT_ROOT, "backend", "data", "login")

# Account identifier used in SAU cookie filenames: cookies/{platform}_{VIDDUB_ACCOUNT}.json
VIDDUB_ACCOUNT = "viddub"


# ── Descriptor ──

@dataclass(frozen=True)
class PlatformDescriptor:
    """Static metadata for a publishable platform."""

    platform_id: str
    display_name: str
    brand_color: str       # hex (no #) for frontend logo background
    logo_text: str         # 1-char short label for avatar fallback

    # Cookie / storage_state file path (absolute)
    cookie_file: str

    # Dispatch metadata
    login_kind: str        # "sau_qrcode_callback" | "biliup_cli" | "viddub_playwright"
    publisher_module: str  # e.g. "app.services.publish.douyin"
    publisher_class: str   # e.g. "DouyinPublisher"
    login_module: str      # e.g. "app.services.platform.douyin"
    login_class: str       # e.g. "DouyinLogin"


def _sau_cookie(filename: str) -> str:
    return os.path.join(SAU_COOKIES_DIR, filename)


# ── Registry ──

_REGISTRY: dict[str, PlatformDescriptor] = {
    "douyin": PlatformDescriptor(
        platform_id="douyin",
        display_name="抖音",
        brand_color="000000",
        logo_text="斗",
        cookie_file=_sau_cookie(f"douyin_{VIDDUB_ACCOUNT}.json"),
        login_kind="sau_qrcode_callback",
        publisher_module="app.services.publish.douyin",
        publisher_class="DouyinPublisher",
        login_module="app.services.platform.douyin",
        login_class="DouyinLogin",
    ),
    "bilibili": PlatformDescriptor(
        platform_id="bilibili",
        display_name="哔哩哔哩",
        brand_color="fb7299",
        logo_text="B",
        cookie_file=_sau_cookie(f"bilibili_{VIDDUB_ACCOUNT}.json"),
        login_kind="biliup_cli",
        publisher_module="app.services.publish.sau_bilibili",
        publisher_class="SauBilibiliPublisher",
        login_module="app.services.platform.bilibili",
        login_class="BilibiliLogin",
    ),
    "kuaishou": PlatformDescriptor(
        platform_id="kuaishou",
        display_name="快手",
        brand_color="ff4906",
        logo_text="快",
        cookie_file=_sau_cookie(f"kuaishou_{VIDDUB_ACCOUNT}.json"),
        login_kind="sau_qrcode_callback",
        publisher_module="app.services.publish.kuaishou",
        publisher_class="KuaishouPublisher",
        login_module="app.services.platform.kuaishou",
        login_class="KuaishouLogin",
    ),
    "tencent": PlatformDescriptor(
        platform_id="tencent",
        display_name="微信视频号",
        brand_color="07c160",
        logo_text="微",
        cookie_file=_sau_cookie(f"tencent_{VIDDUB_ACCOUNT}.json"),
        login_kind="sau_qrcode_callback",
        publisher_module="app.services.publish.tencent",
        publisher_class="TencentPublisher",
        login_module="app.services.platform.tencent",
        login_class="TencentLogin",
    ),
    "xiaohongshu": PlatformDescriptor(
        platform_id="xiaohongshu",
        display_name="小红书",
        brand_color="ff2442",
        logo_text="红",
        cookie_file=_sau_cookie(f"xiaohongshu_{VIDDUB_ACCOUNT}.json"),
        login_kind="sau_qrcode_callback",
        publisher_module="app.services.publish.xiaohongshu",
        publisher_class="XiaohongshuPublisher",
        login_module="app.services.platform.xiaohongshu",
        login_class="XiaohongshuLogin",
    ),
}


# ── Public API ──

def all_platforms() -> tuple[str, ...]:
    """Return all registered platform ids (insertion order)."""
    return tuple(_REGISTRY.keys())


def get(platform_id: str) -> PlatformDescriptor:
    """Return the descriptor for a platform id. Raises ValueError if unknown."""
    if platform_id not in _REGISTRY:
        raise ValueError(f"Unsupported platform: {platform_id}")
    return _REGISTRY[platform_id]


def cookie_path(platform_id: str) -> str:
    """Absolute path to the platform's cookie/storage_state file."""
    return get(platform_id).cookie_file


def display_name(platform_id: str) -> str:
    return get(platform_id).display_name


def display_name_map() -> dict[str, str]:
    """Mapping of platform_id → Chinese display name (for API responses)."""
    return {pid: d.display_name for pid, d in _REGISTRY.items()}


def is_sau_native(platform_id: str) -> bool:
    """True if the platform uses SAU's cookie file format (not viddub storage_state)."""
    return get(platform_id).login_kind != "viddub_playwright"
