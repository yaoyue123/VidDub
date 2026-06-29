"""Drop ixigua platform support

Revision ID: e2f3a4b5c6d7
Revises: c9d0e1f2a3b4
Create Date: 2026-06-29
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "e2f3a4b5c6d7"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Delete all ixigua publish records
    op.execute("DELETE FROM publish_records WHERE platform = 'ixigua'")
    # Remove ixigua-specific config entry
    op.execute("DELETE FROM app_config WHERE key = 'ixigua_default_copyright'")


def downgrade() -> None:
    # Historical publish records cannot be restored.
    # Re-seed the config row so rollback keeps the app functional.
    op.execute("""
        INSERT OR IGNORE INTO app_config (key, value, description)
        VALUES ('ixigua_default_copyright', 'repost',
                '西瓜视频默认版权类型 (original=原创 / repost=转载)')
    """)
