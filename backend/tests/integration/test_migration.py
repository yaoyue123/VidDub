"""Integration test for Phase 4 Alembic migration (P4-30)."""
import os
import tempfile

import pytest
from sqlalchemy import create_engine, text, inspect


@pytest.fixture
def sqlite_path(tmp_path):
    """临时 SQLite 文件，预先建好 schema + Phase 3 旧行."""
    db_path = tmp_path / "test.db"
    eng = create_engine(f"sqlite:///{db_path}")

    # 建表（模拟 Phase 3 完成 schema）
    with eng.begin() as conn:
        conn.execute(text("""
            CREATE TABLE configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key VARCHAR(128) NOT NULL UNIQUE,
                value TEXT,
                description VARCHAR(256),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status VARCHAR(32) NOT NULL,
                title VARCHAR(512),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # 插入旧状态数据
        for status in ("pending", "transcribing", "dubbing", "dubbed", "uploading", "completed"):
            conn.execute(text("INSERT INTO videos (status, title) VALUES (:s, :t)"),
                        {"s": status, "t": f"test-{status}"})

    eng.dispose()
    return str(db_path)


def _run_migration(db_path: str, monkeypatch=None):
    """用 alembic 命令行执行 upgrade head."""
    from alembic.config import Config
    from alembic import command
    from app.core import config as app_config

    test_url = f"sqlite+aiosqlite:///{db_path.replace(os.sep, '/')}"
    # env.py 会用 settings.database_url 覆盖 alembic.ini 的值，必须 patch settings
    if monkeypatch:
        monkeypatch.setattr(app_config.settings, "database_url", test_url)
    else:
        app_config.settings.database_url = test_url

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", test_url)
    command.stamp(cfg, "e6f7a8b2c4d0")
    command.upgrade(cfg, "head")


def test_phase4_migration_maps_legacy_status(sqlite_path, monkeypatch):
    """旧 status 应正确映射到新状态."""
    _run_migration(sqlite_path, monkeypatch)

    eng = create_engine(f"sqlite:///{sqlite_path}")
    with eng.connect() as conn:
        # transcribing → transcribed
        rows = conn.execute(text("SELECT status FROM videos WHERE title='test-transcribing'")).fetchall()
        assert rows[0][0] == "transcribed"

        # dubbing → synthesized
        rows = conn.execute(text("SELECT status FROM videos WHERE title='test-dubbing'")).fetchall()
        assert rows[0][0] == "synthesized"

        # dubbed / uploading → completed
        rows = conn.execute(text("SELECT status FROM videos WHERE title='test-dubbed'")).fetchall()
        assert rows[0][0] == "completed"
        rows = conn.execute(text("SELECT status FROM videos WHERE title='test-uploading'")).fetchall()
        assert rows[0][0] == "completed"

        # 不动旧 pending/completed
        rows = conn.execute(text("SELECT status FROM videos WHERE title='test-pending'")).fetchall()
        assert rows[0][0] == "pending"
        rows = conn.execute(text("SELECT status FROM videos WHERE title='test-completed'")).fetchall()
        assert rows[0][0] == "completed"

    eng.dispose()


def test_phase4_migration_inserts_configs(sqlite_path, monkeypatch):
    """6 个 Phase 4 配置项应存在."""
    _run_migration(sqlite_path, monkeypatch)

    eng = create_engine(f"sqlite:///{sqlite_path}")
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT key FROM configs WHERE key IN "
            "('whisper_model','stt_model','tts_voice_simple',"
            "'translation_context_window','atempo_min','atempo_max')"
        )).fetchall()
        keys = {r[0] for r in rows}
        assert "whisper_model" in keys
        assert "stt_model" in keys
        assert "tts_voice_simple" in keys
        assert "translation_context_window" in keys
        assert "atempo_min" in keys
        assert "atempo_max" in keys
        assert len(keys) == 6

    eng.dispose()


def test_phase4_migration_idempotent(sqlite_path, monkeypatch):
    """重复 upgrade 幂等（不报错、不重复插入）."""
    _run_migration(sqlite_path, monkeypatch)
    # 再执行一次（先降回，再升）
    from alembic.config import Config
    from alembic import command
    from app.core import config as app_config
    test_url = f"sqlite+aiosqlite:///{sqlite_path.replace(os.sep, '/')}"
    monkeypatch.setattr(app_config.settings, "database_url", test_url)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", test_url)
    command.downgrade(cfg, "e6f7a8b2c4d0")
    command.upgrade(cfg, "head")

    eng = create_engine(f"sqlite:///{sqlite_path}")
    with eng.connect() as conn:
        # whisper_model 应只有 1 条
        rows = conn.execute(text("SELECT COUNT(*) FROM configs WHERE key='whisper_model'")).fetchall()
        assert rows[0][0] == 1

    eng.dispose()


def test_phase4_migration_downgrade_reversible(sqlite_path, monkeypatch):
    """downgrade 应可逆恢复旧状态值（不删配置）."""
    _run_migration(sqlite_path, monkeypatch)

    from alembic.config import Config
    from alembic import command
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{sqlite_path}")
    command.downgrade(cfg, "e6f7a8b2c4d0")

    eng = create_engine(f"sqlite:///{sqlite_path}")
    with eng.connect() as conn:
        # synthesized → dubbing 反向
        rows = conn.execute(text("SELECT status FROM videos WHERE title='test-dubbing'")).fetchall()
        assert rows[0][0] == "dubbing"

    eng.dispose()


def test_enums_constants():
    """枚举常量值正确."""
    from app.models.enums import VideoStatus, TaskType
    assert VideoStatus.COMPOSED == "composed"
    assert VideoStatus.SYNTHESIZED == "synthesized"
    assert TaskType.SYNTHESIZE == "synthesize"
    assert TaskType.COMPOSE == "compose"
