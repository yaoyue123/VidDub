"""add dubbed_filepath to videos

Revision ID: e6f7a8b2c4d0
Revises: d4c2e8a1b3f5
Create Date: 2026-06-15 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6f7a8b2c4d0'
down_revision: Union[str, None] = 'd4c2e8a1b3f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('videos', sa.Column('dubbed_filepath', sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column('videos', 'dubbed_filepath')
