"""phase9 channels + scan_logs + videos.deleted_at

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-22 12:00:00.000000

迁移内容 (per D9-03, D9-04, D9-07, D9-08):
1. 新建 channels 表 (幂等 create_table checkfirst=True)
2. 新建 scan_logs 表 (幂等 create_table checkfirst=True)
3. videos 表新增 deleted_at 列 (软删除, D9-08)
4. 新增 Phase 9 配置项 (scan_max_concurrent / scan_default_interval_hours)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PHASE9_CONFIGS = [
    ("scan_max_concurrent", "3",
     "频道扫描最大并发数"),
    ("scan_default_interval_hours", "6",
     "频道默认扫描间隔小时数 (1/3/6/12/24)"),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # ── 1. channels 表 (D9-03) ──
    if 'channels' not in existing_tables:
        op.create_table(
            'channels',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(length=128), nullable=False, comment='频道别名'),
            sa.Column('url', sa.String(length=512), nullable=False, comment='频道 URL'),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
            sa.Column('scan_interval_hours', sa.Integer(), nullable=False, server_default='6'),
            sa.Column('last_scanned_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('filter_min_views', sa.Integer(), nullable=True),
            sa.Column('filter_max_duration_sec', sa.Integer(), nullable=True),
            sa.Column('filter_min_duration_sec', sa.Integer(), nullable=True),
            sa.Column('auto_publish', sa.Boolean(), nullable=False, server_default=sa.text('0')),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True),
                      server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.UniqueConstraint('url', name='uq_channels_url'),
        )
        op.create_index('ix_channels_enabled', 'channels', ['enabled'])
    else:
        # 表已存在但索引可能缺 — 补建
        ch_indexes = {idx["name"] for idx in inspector.get_indexes('channels')}
        if 'ix_channels_enabled' not in ch_indexes:
            op.create_index('ix_channels_enabled', 'channels', ['enabled'])

    # ── 2. scan_logs 表 (D9-07) ──
    if 'scan_logs' not in existing_tables:
        op.create_table(
            'scan_logs',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('channel_id', sa.Integer(),
                      sa.ForeignKey('channels.id', ondelete='CASCADE'),
                      nullable=False, index=True),
            sa.Column('scanned_at', sa.DateTime(timezone=True),
                      server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('found_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('added_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('error_msg', sa.Text(), nullable=True),
        )
        # ix_scan_logs_channel_id 已由 Column(index=True) 自动创建，不重复声明
        existing_indexes = {idx["name"] for idx in inspector.get_indexes('scan_logs')}
        if 'ix_scan_logs_scanned_at' not in existing_indexes:
            op.create_index('ix_scan_logs_scanned_at', 'scan_logs', ['scanned_at'])

    # ── 3. videos.deleted_at 软删除 (D9-08) ──
    existing_cols = {c["name"] for c in inspector.get_columns("videos")}
    if 'deleted_at' not in existing_cols:
        op.add_column('videos', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    if 'channel_id' not in existing_cols:
        # SQLite 不支持 ALTER TABLE ADD COLUMN 带 FK 约束；FK 在 ORM 层声明即可（SQLite 默认不强制 FK）
        op.add_column('videos',
                      sa.Column('channel_id', sa.Integer(),
                                nullable=True))
    video_indexes = {idx["name"] for idx in inspector.get_indexes('videos')}
    if 'ix_videos_channel_id' not in video_indexes:
        op.create_index('ix_videos_channel_id', 'videos', ['channel_id'])
    if 'source' not in existing_cols:
        # 'manual' / 'channel' — 区分手动添加和频道扫描添加
        op.add_column('videos',
                      sa.Column('source', sa.String(length=16),
                                nullable=False, server_default='manual'))

    # ── 4. 配置项幂等 INSERT ──
    dialect = bind.dialect.name
    for key, value, desc in PHASE9_CONFIGS:
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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if 'scan_logs' in existing_tables:
        try:
            op.drop_table('scan_logs')
        except Exception:
            pass

    if 'channels' in existing_tables:
        try:
            op.drop_table('channels')
        except Exception:
            pass

    existing_cols = {c["name"] for c in inspector.get_columns("videos")} if 'videos' in existing_tables else set()
    for col in ('deleted_at', 'channel_id', 'source'):
        if col in existing_cols:
            try:
                op.drop_column('videos', col)
            except Exception:
                pass
