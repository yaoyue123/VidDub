"""phase8 ai_title_fields

Revision ID: b8c9d0e1f2a3
Revises: a1b2c3d4e5f6
Create Date: 2026-06-22 11:00:00.000000

迁移内容 (per D8-09, D8-10):
1. videos 表新增 4 列（幂等 add_column with checkfirst）：
   - ai_title_candidates TEXT (JSON array of strings)
   - ai_tags_candidates  TEXT (JSON array of strings)
   - title_chosen        VARCHAR(200)
   - tags_chosen         TEXT (JSON array)
2. 新增 Phase 8 配置项 (title_generator_enabled /
   title_generator_candidate_count / title_generator_tag_count)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Phase 8 配置项 (D8-04 toggle + D8-02/D8-03 counts)
PHASE8_CONFIGS = [
    ("title_generator_enabled", "true",
     "AI 标题/标签自动生成开关 (true/false)，配音完成后自动触发"),
    ("title_generator_candidate_count", "5",
     "AI 候选标题数量 (默认 5)"),
    ("title_generator_tag_count", "8",
     "AI 候选标签数量 (默认 8，Bilibili 上限 10，留 2 个空位给默认标签)"),
]


# 待新增列定义 (name, Column)
_NEW_COLUMNS = [
    ("ai_title_candidates", sa.Text(), "ai_title_candidates"),
    ("ai_tags_candidates", sa.Text(), "ai_tags_candidates"),
    ("title_chosen", sa.String(length=200), "title_chosen"),
    ("tags_chosen", sa.Text(), "tags_chosen"),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── 1. 幂等 add_column ──
    existing_cols = {c["name"] for c in inspector.get_columns("videos")}
    for col_name, col_type, _ in _NEW_COLUMNS:
        if col_name not in existing_cols:
            op.add_column("videos", sa.Column(col_name, col_type, nullable=True))
        # else: 已存在则跳过 (幂等)

    # ── 2. 配置项幂等 INSERT ──
    dialect = bind.dialect.name
    for key, value, desc in PHASE8_CONFIGS:
        if dialect == 'sqlite':
            op.execute(
                sa.text(
                    "INSERT OR IGNORE INTO configs (key, value, description, created_at, updated_at) "
                    "VALUES (:k, :v, :d, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ).bindparams(k=key, v=value, d=desc)
            )
        else:
            op.execute(
                sa.text(
                    "INSERT INTO configs (key, value, description, created_at, updated_at) "
                    "VALUES (:k, :v, :d, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) "
                    "ON CONFLICT (key) DO NOTHING"
                ).bindparams(k=key, v=value, d=desc)
            )


def downgrade() -> None:
    for col_name, _col_type, _ in reversed(_NEW_COLUMNS):
        # op.drop_column 本身幂等性差，try/except 保护
        try:
            op.drop_column("videos", col_name)
        except Exception:
            pass
    # 不删除配置项（保留兼容）
