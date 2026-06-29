from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug)


# ── SQLite performance pragmas on every connection (D-INFRA-02) ──

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragmas(dbapi_connection, connection_record):
    """Set performance and safety pragmas on every new SQLite connection.

    - WAL journal mode for concurrent read performance
    - busy_timeout=5000 to prevent "database is locked" errors
    - synchronous=NORMAL for balanced durability (safe with WAL)
    - foreign_keys=ON to ensure FK constraint enforcement
    - cache_size=-64000 for 64MB page cache
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA cache_size=-64000")
    cursor.close()


async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Indexes for tracking query patterns (D-INFRA-02) ──

_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS ix_videos_created_at ON videos(created_at)",
    "CREATE INDEX IF NOT EXISTS ix_videos_view_count ON videos(view_count)",
    "CREATE INDEX IF NOT EXISTS ix_videos_channel_id ON videos(channel_id)",
    "CREATE INDEX IF NOT EXISTS ix_videos_source ON videos(source)",
    "CREATE INDEX IF NOT EXISTS ix_discovery_results_source_id ON discovery_results(source_id)",
    "CREATE INDEX IF NOT EXISTS ix_discovery_results_youtube_id ON discovery_results(youtube_id)",
    "CREATE INDEX IF NOT EXISTS ix_discovery_results_discovered_at ON discovery_results(discovered_at)",
    "CREATE INDEX IF NOT EXISTS ix_discovery_results_status ON discovery_results(status)",
]


def _ensure_indexes(connection) -> None:
    """Create all tracking query pattern indexes using IF NOT EXISTS."""
    for sql in _INDEX_SQL:
        connection.execute(text(sql))


def init_db(connection) -> None:
    """Initialize database schema: indexes, FTS5 virtual table, and migrations.

    Call from main.py lifespan after Base.metadata.create_all.
    Runs idempotently via IF NOT EXISTS clauses.
    """
    _ensure_indexes(connection)
    _ensure_fts5(connection)
    _ensure_discovery_columns(connection)


# ── Schema migration: Phase 8 discovery columns (D-INFRA-03) ──

_DISCOVERY_MIGRATION_SQL = [
    # discovery_sources filter columns (Phase 8-01)
    "ALTER TABLE discovery_sources ADD COLUMN filter_min_views INTEGER",
    "ALTER TABLE discovery_sources ADD COLUMN filter_max_views INTEGER",
    "ALTER TABLE discovery_sources ADD COLUMN filter_min_duration_sec INTEGER",
    "ALTER TABLE discovery_sources ADD COLUMN filter_max_duration_sec INTEGER",
    "ALTER TABLE discovery_sources ADD COLUMN filter_published_within_hours INTEGER",
    # discovery_results display metadata columns (Phase 8-01)
    "ALTER TABLE discovery_results ADD COLUMN view_count INTEGER",
    "ALTER TABLE discovery_results ADD COLUMN like_count INTEGER",
    "ALTER TABLE discovery_results ADD COLUMN thumbnail_url VARCHAR(512)",
    "ALTER TABLE discovery_results ADD COLUMN published_at VARCHAR(64)",
    "ALTER TABLE discovery_results ADD COLUMN duration_sec INTEGER",
]


def _ensure_discovery_columns(connection) -> None:
    """Add Phase 8 discovery columns if they don't exist yet.

    SQLite ALTER TABLE ADD COLUMN with IF NOT EXISTS isn't supported,
    so we catch 'duplicate column' errors and continue.
    """
    for sql in _DISCOVERY_MIGRATION_SQL:
        try:
            connection.execute(text(sql))
        except Exception:
            # Column already exists — skip (SQLite lacks IF NOT EXISTS for ALTER TABLE)
            pass


# ── FTS5 virtual table for keyword search (D-INFRA-02) ──

_FTS5_CREATE_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS videos_fts USING fts5(
    title, description, channel,
    content='videos',
    content_rowid='id'
)
"""

_FTS5_TRIGGERS_SQL = [
    # AFTER INSERT: sync new video into FTS index
    """
    CREATE TRIGGER IF NOT EXISTS tr_videos_fts_ai AFTER INSERT ON videos BEGIN
        INSERT INTO videos_fts(rowid, title, description, channel)
        VALUES (new.id, new.title, new.description, new.channel);
    END
    """,
    # AFTER DELETE: remove deleted video from FTS index
    """
    CREATE TRIGGER IF NOT EXISTS tr_videos_fts_ad AFTER DELETE ON videos BEGIN
        INSERT INTO videos_fts(videos_fts, rowid, title, description, channel)
        VALUES('delete', old.id, old.title, old.description, old.channel);
    END
    """,
    # AFTER UPDATE: remove old entry, insert new entry
    """
    CREATE TRIGGER IF NOT EXISTS tr_videos_fts_au AFTER UPDATE ON videos BEGIN
        INSERT INTO videos_fts(videos_fts, rowid, title, description, channel)
        VALUES('delete', old.id, old.title, old.description, old.channel);
        INSERT INTO videos_fts(rowid, title, description, channel)
        VALUES (new.id, new.title, new.description, new.channel);
    END
    """,
]


def _ensure_fts5(connection) -> None:
    """Create FTS5 virtual table, content-sync triggers, and populate initial data."""
    # Create virtual table
    connection.execute(text(_FTS5_CREATE_SQL))

    # Create content-sync triggers
    for sql in _FTS5_TRIGGERS_SQL:
        connection.execute(text(sql))

    # Initial population: copy existing videos into FTS index
    connection.execute(text(
        "INSERT OR IGNORE INTO videos_fts(rowid, title, description, channel) "
        "SELECT id, title, description, channel FROM videos"
    ))
