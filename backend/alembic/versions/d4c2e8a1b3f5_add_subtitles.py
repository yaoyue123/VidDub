"""add subtitles table

Revision ID: d4c2e8a1b3f5
Revises: 85e4114b41ec
Create Date: 2026-06-15 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4c2e8a1b3f5'
down_revision: Union[str, None] = '85e4114b41ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('subtitles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('video_id', sa.Integer(), nullable=False),
        sa.Column('language', sa.String(length=16), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False, server_default='whisper', comment='whisper / manual / translation'),
        sa.Column('content', sa.Text(), nullable=True, comment='SRT or JSON formatted subtitle content'),
        sa.Column('filepath', sa.String(length=1024), nullable=True, comment='Path to SRT file on disk'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_subtitles_video_id'), 'subtitles', ['video_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_subtitles_video_id'), table_name='subtitles')
    op.drop_table('subtitles')
