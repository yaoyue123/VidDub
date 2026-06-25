"""Phase 7 平台发布抽象基类 (B5, D7-04).

每个平台发布流程 (D7-04 单平台流程)：
1. 加载 storage_state 创建 Playwright BrowserContext
2. 导航到上传页
3. 上传视频文件
4. 等待视频处理完成
5. 填写标题、描述、标签、封面
6. 选择分区/分类
7. 点击提交
8. 检测成功
9. 保存返回的平台视频 URL

子类需要实现具体的 DOM 操作。
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Optional


# ── 上传超时（D7-04 Claude's Discretion）──
UPLOAD_TIMEOUT_SEC = 10 * 60   # 10 分钟等待上传 + 处理
PROGRESS_POLL_INTERVAL = 5     # 进度轮询频率 5s


@dataclass
class PublishFields:
    """填表内容 (D7-03)."""
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    cover_path: Optional[str] = None
    # 哔哩哔哩分区 tid (默认 122=野生技术协会)
    category_id: Optional[str] = None
    category_label: Optional[str] = None
    # 西瓜视频原创/转载 (original/repost)
    copyright_type: Optional[str] = None
    # 转载时填的原视频 URL
    source_url: Optional[str] = None


@dataclass
class PublishResult:
    """单次发布的返回结果."""
    success: bool
    platform_video_url: Optional[str] = None
    error_msg: Optional[str] = None
    needs_relogin: bool = False
    # 截图路径（DOM 失败时保留诊断）
    screenshot_path: Optional[str] = None


class PlatformPublisher(abc.ABC):
    """平台发布抽象基类 (D7-04)."""

    platform: str = "base"

    @abc.abstractmethod
    async def publish(self, video_id: int, fields: PublishFields,
                      video_file_path: str,
                      progress_callback: Optional[Any] = None) -> PublishResult:
        """发布一个视频到平台.

        Args:
            video_id: 内部 video.id
            fields: 填表内容
            video_file_path: 待上传的 mp4 文件绝对路径
            progress_callback: 可选回调 async (stage, pct) -> None
        Returns:
            PublishResult
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def validate_login(self) -> bool:
        """检查本地 storage_state 是否仍登录 (复用 Phase 6 LoginManager)."""
        raise NotImplementedError

    @staticmethod
    def _safe_text(s: str, max_len: int) -> str:
        """截断字符串到 max_len，避免超长被平台拒绝."""
        if not s:
            return ""
        return s[:max_len]
