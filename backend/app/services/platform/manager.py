"""Login manager (Phase 6, B6).

LoginManager 单例职责：
- 按 platform 名返回对应的 PlatformLoginBase 实例
- 加载 / 保存 storage_state JSON 文件（仅用于 transitional viddub_playwright 平台）

平台元数据（路径、模块、登录方式）由 `app.services.platforms.registry`
统一管理；本类只保留实例缓存 + 给 viddub_playwright 平台使用的旧 storage_state
加载/保存接口。

文件命名（D6-05, D6-12）：
- ixigua_storage_state.json  (transitional, 待 P5 删除)
- {platform}_{account_id}_storage_state.json  (多账号接口预留)
"""
from __future__ import annotations

import importlib
import json
import logging
import os
from typing import Optional

from app.services.platform.base import PlatformLoginBase
from app.services.platforms.registry import (
    VIDDUB_LOGIN_DATA_DIR,  # exported via registry for transitional use
    all_platforms,
    cookie_path,
    get as get_descriptor,
)

logger = logging.getLogger(__name__)


# 默认 storage_state 目录（保留给 transitional viddub_playwright 平台使用）
DEFAULT_LOGIN_DATA_DIR = VIDDUB_LOGIN_DATA_DIR


def _resolve_data_dir(override: Optional[str] = None) -> str:
    if override:
        path = override
    else:
        path = os.environ.get("PLATFORM_LOGIN_DATA_DIR", DEFAULT_LOGIN_DATA_DIR)
    os.makedirs(path, exist_ok=True)
    return path


class LoginManager:
    """登录管理器：按平台名分发登录器实例 + 持久化 storage_state (legacy)."""

    SUPPORTED_PLATFORMS = all_platforms()

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self.data_dir = _resolve_data_dir(data_dir)
        self._instances: dict[str, PlatformLoginBase] = {}
        self._last_user_info: dict[str, dict] = {}

    # ── 路径辅助（仅用于 transitional viddub_playwright 平台）──

    def _storage_state_path_or_none(
        self, platform: str, account_id: Optional[str] = None
    ) -> Optional[str]:
        """Return the storage_state path, or None if platform is unknown."""
        try:
            descriptor = get_descriptor(platform)
        except ValueError:
            return None
        if descriptor.login_kind != "viddub_playwright":
            return descriptor.cookie_file
        if account_id:
            fname = f"{platform}_{account_id}_storage_state.json"
        else:
            fname = f"{platform}_storage_state.json"
        return os.path.join(self.data_dir, fname)

    def storage_state_path(self, platform: str, account_id: Optional[str] = None) -> str:
        """Public method — returns path or raises ValueError for unknown platform."""
        return get_descriptor(platform).cookie_file

    # ── storage_state 加载 / 保存 (legacy, 仅 transitional 用) ──

    def load_storage_state(self, platform: str, account_id: Optional[str] = None) -> Optional[dict]:
        path = self._storage_state_path_or_none(platform, account_id)
        if path is None:
            return None
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
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        logger.info("Saved storage_state for %s -> %s", platform, path)
        return path

    def clear_storage_state(self, platform: str, account_id: Optional[str] = None) -> bool:
        path = self._storage_state_path_or_none(platform, account_id)
        if path is None:
            return False
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
        descriptor = get_descriptor(platform)  # raises ValueError for unknown
        if platform in self._instances:
            return self._instances[platform]

        path = descriptor.cookie_file
        module = importlib.import_module(descriptor.login_module)
        cls = getattr(module, descriptor.login_class)
        inst = cls(storage_state_path=path)

        self._instances[platform] = inst
        return inst


# 模块级单例（API 层共用）
_manager: Optional[LoginManager] = None


def get_login_manager() -> LoginManager:
    global _manager
    if _manager is None:
        _manager = LoginManager()
    return _manager
