"""phase4 dubbing pipeline

Revision ID: f8a9b0c3d1e2
Revises: e6f7a8b2c4d0
Create Date: 2026-06-17 23:30:00.000000

迁移内容（per D-13/D-14/D-15, ADDENDUM D-17）：
1. 数据迁移：videos.status 旧值 → 新值（非破坏性 UPDATE）
2. 配置项：INSERT OR IGNORE 6 个 Phase 4 新键

注意：videos.status / tasks.type 仍是 String(32)，无 SQL Enum 约束，
无需 ALTER COLUMN（per RESEARCH §Data Model Migration）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f8a9b0c3d1e2'
down_revision: Union[str, None] = 'e6f7a8b2c4d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── 状态映射（D-13 + CONTEXT pivot） ──
STATUS_MAP = [
    # (旧值, 新值, 原因)
    ("transcribing", "transcribed", "Phase 3 中间态统一映射到新状态机"),
    ("dubbing", "synthesized", "旧 dubbing 阶段对应新 TTS+align 步骤完成"),
    ("dubbed", "completed", "旧终态"),
    ("uploading", "completed", "上传相关状态在 Phase 4 不再使用"),
]

# Phase 4 配置项（key, value, description）
PHASE4_CONFIGS = [
    ("whisper_model", "tiny", "本地 Whisper 模型 (tiny/base/small/medium)"),
    ("stt_model", "whisper-local", "STT 后端标识（实际用本地 Whisper）"),
    ("tts_voice_simple", "alex", "TTS 默认音色"),
    ("translation_context_window", "2", "翻译滑窗上下文段数"),
    ("atempo_min", "0.7", "atempo 调速下限"),
    ("atempo_max", "1.5", "atempo 调速上限"),
]


def upgrade() -> None:
    # 1. 数据迁移：videos.status 旧值 → 新值（仅对存在的旧行操作，不影响新行）
    for old, new, _reason in STATUS_MAP:
        op.execute(
            sa.text(
                "UPDATE videos SET status = :new WHERE status = :old"
            ).bindparams(new=new, old=old)
        )

    # 2. 配置项幂等 INSERT（INSERT OR IGNORE for SQLite；其他方言用 INSERT ... ON CONFLICT）
    #    SQLite 默认行为：UNIQUE 约束冲突时 INSERT 失败 → 用 INSERT OR IGNORE
    bind = op.get_bind()
    dialect = bind.dialect.name

    for key, value, desc in PHASE4_CONFIGS:
        if dialect == "sqlite":
            op.execute(
                sa.text(
                    "INSERT OR IGNORE INTO configs (key, value, description, created_at, updated_at) "
                    "VALUES (:k, :v, :d, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ).bindparams(k=key, v=value, d=desc)
            )
        else:
            # PostgreSQL / 其他：用 ON CONFLICT DO NOTHING
            op.execute(
                sa.text(
                    "INSERT INTO configs (key, value, description, created_at, updated_at) "
                    "VALUES (:k, :v, :d, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) "
                    "ON CONFLICT (key) DO NOTHING"
                ).bindparams(k=key, v=value, d=desc)
            )


def downgrade() -> None:
    # 反向：新值 → 旧值（仅恢复旧映射，不删配置项保留兼容）
    for old, new, _reason in STATUS_MAP:
        op.execute(
            sa.text(
                "UPDATE videos SET status = :old WHERE status = :new"
            ).bindparams(old=old, new=new)
        )
    # 不删除 Phase 4 配置项（保留兼容；用户可手动删除）
