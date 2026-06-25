"""Phase 4 状态机枚举常量 (D-13, D-14).

Video/Task 列在 schema 层仍是 String(32)（无 SQL Enum 约束），
这里只是 Python 常量，方便引用避免拼写错误。

per ADDENDUM + CONTEXT pivot：去除 separating/mixed/separate/mix。
"""


class VideoStatus:
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    # WR-07: 新增 in-flight 中间态，避免 _handle_transcribe 复用 DOWNLOADING
    # （会与 D-13 状态机冲突，导致 CLI status poll 误以为是下载阶段）。
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    TRANSLATED = "translated"
    SYNTHESIZED = "synthesized"
    COMPOSED = "composed"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskType:
    DOWNLOAD = "download"
    TRANSCRIBE = "transcribe"
    TRANSLATE = "translate"
    SYNTHESIZE = "synthesize"
    COMPOSE = "compose"


class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# 旧状态 → 新状态映射（迁移用）
LEGACY_VIDEO_STATUS_MAP = {
    "transcribing": VideoStatus.TRANSCRIBED,
    "dubbing": VideoStatus.SYNTHESIZED,
    "dubbed": VideoStatus.COMPLETED,
    "uploading": VideoStatus.COMPLETED,
    # 'separating'/'mixed' 不存在于现存数据，无需映射
}
