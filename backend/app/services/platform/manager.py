"""Login manager (Phase 6, B6).

LoginManager 单例职责：
- 按 platform 名返回对应的 PlatformLoginBase 实例
- 管理 storage_state 目录 (backend/data/login/)
- 加载 / 保存 storage_state JSON 文件

文件命名（D6-05, D6-12）：
- ixigua_storage_state.json
- bilibili_storage_state.json
- {platform}_{account_id}_storage_state.json  (多账号接口预留)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from app.services.platform.base import PlatformLoginBase

logger = logging.getLogger(__name__)


# 默认 storage_state 目录（相对于 backend cwd）
DEFAULT_LOGIN_DATA_DIR = os.path.join("backend", "data", "login")


def _resolve_data_dir(override: Optional[str] = None) -> str:
    if override:
        path = override
    else:
        # 优先从环境变量读取（settings 可注入）
        path = os.environ.get("PLATFORM_LOGIN_DATA_DIR", DEFAULT_LOGIN_DATA_DIR)
    os.makedirs(path, exist_ok=True)
    return path


class LoginManager:
    """登录管理器：按平台名分发登录器实例 + 持久化 storage_state."""

    SUPPORTED_PLATFORMS = ("ixigua", "bilibili")

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self.data_dir = _resolve_data_dir(data_dir)
        # 登录器缓存：platform -> PlatformLoginBase
        self._instances: dict[str, PlatformLoginBase] = {}
        # 保存最近一次登录会话的用户信息（供 UI 展示）
        self._last_user_info: dict[str, dict] = {}

    # ── 路径辅助 ──

    def storage_state_path(self, platform: str, account_id: Optional[str] = None) -> str:
        """返回 storage_state 文件绝对路径.

        - 单账号：{data_dir}/{platform}_storage_state.json
        - 多账号：{data_dir}/{platform}_{account_id}_storage_state.json
        """
        if account_id:
            fname = f"{platform}_{account_id}_storage_state.json"
        else:
            fname = f"{platform}_storage_state.json"
        return os.path.join(self.data_dir, fname)

    # ── storage_state 加载 / 保存 ──

    def load_storage_state(self, platform: str, account_id: Optional[str] = None) -> Optional[dict]:
        path = self.storage_state_path(platform, account_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to load storage_state for %s: %s", platform, e)
            return None

    def save_storage_state(
        self, platform: str, state: dict, account_id: Optional[str] = None
    ) -> str:
        path = self.storage_state_path(platform, account_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # 原子写：先写 .tmp 再 rename
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        logger.info("Saved storage_state for %s -> %s", platform, path)
        return path

    def clear_storage_state(self, platform: str, account_id: Optional[str] = None) -> bool:
        path = self.storage_state_path(platform, account_id)
        if os.path.exists(path):
            try:
                os.remove(path)
                logger.info("Cleared storage_state for %s", platform)
                return True
            except OSError as e:
                logger.warning("Failed to remove storage_state for %s: %s", platform, e)
                return False
        return False

    # ── 登录器实例工厂 ──

    def get(self, platform: str) -> PlatformLoginBase:
        """返回指定平台的登录器实例（单例缓存）."""
        if platform not in self.SUPPORTED_PLATFORMS:
            raise ValueError(f"Unsupported platform: {platform}")

        if platform in self._instances:
            return self._instances[platform]

        # 懒加载具体实现（避免 import 时强依赖 playwright/qrcode）
        path = self.storage_state_path(platform)
        if platform == "bilibili":
            from app.services.platform.bilibili import BilibiliLogin
            inst = BilibiliLogin(storage_state_path=path)
        elif platform == "ixigua":
            from app.services.platform.ixigua import IxiguaLogin
            inst = IxiguaLogin(storage_state_path=path)
        else:  # pragma: no cover — guarded above
            raise ValueError(f"Unsupported platform: {platform}")

        self._instances[platform] = inst
        return inst


# 模块级单例（API 层共用）
_manager: Optional[LoginManager] = None


def get_login_manager() -> LoginManager:
    global _manager
    if _manager is None:
        _manager = LoginManager()
    return _manager
