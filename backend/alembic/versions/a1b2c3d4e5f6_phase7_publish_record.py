"""phase7 publish_record

Revision ID: a1b2c3d4e5f6
Revises: f8a9b0c3d1e2
Create Date: 2026-06-22 10:00:00.000000

迁移内容 (per D7-05, D7-06):
1. 新建表 publish_records (幂等 create_table checkfirst=True)
2. 新增 Phase 7 配置项 (auto_publish_enabled / bilibili_default_category /
   ixigua_default_copyright / publish_default_tags)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f8a9b0c3d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Phase 7 配置项
PHASE7_CONFIGS = [
    ("auto_publish_enabled", "true",
     "配音完成后是否自动发布到平台 (true/false)"),
    ("bilibili_default_category", "122",
     "哔哩哔哩默认分区 tid (122=野生技术协会, 95=数码, 207=科技科普)"),
    ("ixigua_default_copyright", "repost",
     "西瓜视频默认版权类型 (original=原创 / repost=转载)"),
    ("publish_default_tags", "搬运,英语学习,翻译",
     "发布默认标签 (逗号分隔，最多 10 个)"),
    ("publish_retry_max", "3",
     "发布失败最大重试次数"),
    ("publish_upload_timeout_sec", "600",
     "视频上传 + 处理最长等待秒数 (默认 10 分钟)"),
]


def upgrade() -> None:
    # 1. 新建 publish_records 表 (幂等)
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'publish_records' not in inspector.get_table_names():
        op.create_table(
            'publish_records',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('video_id', sa.Integer(),
                      sa.ForeignKey('videos.id', ondelete='CASCADE'),
                      nullable=False, index=True),
            sa.Column('platform', sa.String(32), nullable=False, index=True),
            sa.Column('status', sa.String(32), nullable=False,
                      server_default='pending', index=True),
            sa.Column('platform_video_url', sa.String(512), nullable=True),
            sa.Column('title_used', sa.String(256), nullable=True),
            sa.Column('desc_used', sa.Text(), nullable=True),
            sa.Column('tags_used', sa.String(512), nullable=True),
            sa.Column('cover_path', sa.String(1024), nullable=True),
            sa.Column('category_used', sa.String(64), nullable=True),
            sa.Column('copyright_used', sa.String(32), nullable=True),
            sa.Column('error_msg', sa.Text(), nullable=True),
            sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False),
            sa.Column('needs_relogin', sa.Boolean(),
                      server_default=sa.text('0'), nullable=False),
            sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False,
                      onupdate=sa.func.now()),
        )
        op.create_index(
            'ix_publish_records_video_platform',
            'publish_records',
            ['video_id', 'platform'],
            unique=False,
        )

    # 2. 配置项幂等 INSERT
    dialect = bind.dialect.name
    for key, value, desc in PHASE7_CONFIGS:
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
    op.drop_index('ix_publish_records_video_platform', table_name='publish_records')
    op.drop_table('publish_records')
    # 不删除配置项（保留兼容）
