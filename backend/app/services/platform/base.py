"""Platform login abstract base class (Phase 6, B3).

定义所有平台登录器需要实现的接口：
- start_qr_login: 启动扫码登录，返回二维码图片字节（PNG）
- poll_login_status: 轮询登录状态，返回 status / cookies / user_info
- check_login_status: 使用已保存 storage_state 检测当前是否仍登录
- logout: 清除登录态

常量：超时 5 分钟，二维码 30 秒刷新，storage_state 文件路径。
"""
from __future__ import annotations

import abc
import time
from typing import Any, Optional


# ── 常量（D6-09, D6-11）──
LOGIN_TIMEOUT_SEC = 5 * 60         # 5 分钟无扫码则超时
QR_REFRESH_INTERVAL_SEC = 30       # 二维码每 30 秒刷新一次
LOGIN_POLL_INTERVAL_SEC = 2        # 状态轮询间隔
LOGIN_CHECK_INTERVAL_SEC = 30 * 60  # 每 30 分钟检测一次过期


class LoginStatus:
    """轮询登录状态机取值."""
    WAITING = "waiting"        # 等待扫码
    SCANNED = "scanned"        # 已扫码，等待确认
    SUCCESS = "success"        # 登录成功
    EXPIRED = "expired"        # 二维码过期
    FAILED = "failed"          # 登录失败（其他原因）
    TIMEOUT = "timeout"        # 整体超时


class PlatformLoginBase(abc.ABC):
    """平台登录抽象基类.

    每个具体平台（Bilibili / Ixigua）继承此类并实现四个核心方法。
    子类负责维护自己的 storage_state 文件路径与 QR 数据来源。
    """

    platform_name: str = "base"

    def __init__(self, storage_state_path: str) -> None:
        self.storage_state_path = storage_state_path
        # session 内状态：qrcode_key / start_time / 最近一次 QR 图片字节
        self._session_start_ts: Optional[float] = None
        self._last_qr_refresh_ts: Optional[float] = None

    # ── 会话生命周期辅助 ──

    def _now(self) -> float:
        return time.time()

    def _mark_session_start(self) -> None:
        self._session_start_ts = self._now()
        self._last_qr_refresh_ts = self._now()

    def is_session_expired(self) -> bool:
        """整体会话是否超时（5 分钟）."""
        if self._session_start_ts is None:
            return False
        return (self._now() - self._session_start_ts) > LOGIN_TIMEOUT_SEC

    def needs_qr_refresh(self) -> bool:
        """是否到了刷新二维码的时间（30 秒）."""
        if self._last_qr_refresh_ts is None:
            return True
        return (self._now() - self._last_qr_refresh_ts) >= QR_REFRESH_INTERVAL_SEC

    def _mark_qr_refreshed(self) -> None:
        self._last_qr_refresh_ts = self._now()

    # ── 子类必须实现 ──

    @abc.abstractmethod
    async def start_qr_login(self) -> bytes:
        """启动扫码登录流程，返回 PNG 二维码图片字节."""
        raise NotImplementedError

    @abc.abstractmethod
    async def poll_login_status(self) -> dict[str, Any]:
        """轮询登录状态.

        返回 dict：
            {status: LoginStatus.X, cookies?: dict, user_info?: dict, message?: str}
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def check_login_status(self) -> bool:
        """使用 storage_state 检测当前是否仍处于登录态（不启动 Playwright）."""
        raise NotImplementedError

    @abc.abstractmethod
    async def logout(self) -> None:
        """清除 storage_state 与会话状态."""
        raise NotImplementedError
