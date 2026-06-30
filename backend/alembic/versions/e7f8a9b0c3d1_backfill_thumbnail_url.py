"""backfill NULL thumbnail_url with YouTube deterministic URL

Revision ID: e7f8a9b0c3d1
Revises: f8a9b0c3d1e2
Create Date: 2026-06-30 18:45:00.000000

YouTube thumbnail URL is deterministic from youtube_id:
  https://i.ytimg.com/vi/{youtube_id}/hqdefault.jpg

This migration backfills existing NULL thumbnail_url values for videos
that have a valid youtube_id. New videos created via dub.py now include
thumbnail_url from yt-dlp metadata extraction.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f8a9b0c3d1'
down_revision: Union[str, None] = 'f8a9b0c3d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE videos
        SET thumbnail_url = 'https://i.ytimg.com/vi/' || youtube_id || '/hqdefault.jpg'
        WHERE thumbnail_url IS NULL
          AND youtube_id IS NOT NULL
          AND length(youtube_id) >= 10
        """
    )


def downgrade() -> None:
    # No simple way to undo — the backfill data is valid and deterministic.
    # To revert, run: UPDATE videos SET thumbnail_url = NULL WHERE thumbnail_url LIKE 'https://i.ytimg.com/vi/%'
    pass
