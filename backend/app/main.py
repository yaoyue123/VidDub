import asyncio
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import sys
from typing import AsyncIterator

# Windows: patchright/Playwright 使用 asyncio.create_subprocess_exec 启动 Chromium，
# 必须用 ProactorEventLoop。uvicorn 0.30.0 --reload on Windows switches to
# SelectorEventLoopPolicy (uvicorn.loops.asyncio.asyncio_setup), which breaks
# create_subprocess_exec(). start.bat now passes --loop none to prevent this,
# and we set the ProactorEventLoopPolicy explicitly for defense-in-depth.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Debug log：在 startup 时打印 loop 类型，帮助确认 Proactor 是否生效
def _log_loop_type():
    import logging
    try:
        loop = asyncio.get_running_loop()
        logging.getLogger("app.main").info(
            "Event loop type: %s (is_proactor=%s)",
            type(loop).__name__, isinstance(loop, asyncio.ProactorEventLoop),
        )
    except RuntimeError:
        logging.getLogger("app.main").warning("No event loop in main module body")

# 配置日志（Phase 6 debug: 让 platform/siliconflow 等模块的 INFO 输出可见）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# CR-01: Ensure .env is loaded into os.environ BEFORE Settings is instantiated,
# otherwise the API/uvicorn path has no SILICONFLOW_API_KEY in env (pydantic-settings
# only populates Settings instance attrs from .env; it does NOT touch os.environ).
# cli.py and tests/conftest.py already call load_dotenv() — this mirrors that for uvicorn.
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from app.api.router import api_router
from app.core.config import settings
from app.core.database import engine, Base, async_session_factory
from app.core.websocket import manager as ws_manager
from app.services.scheduler import TaskScheduler
from app.services.config_seeder import seed_default_config
from app.services.channel_scanner import ChannelScanner, set_channel_scanner


# ── Global scheduler instance ──

scheduler: TaskScheduler | None = None
channel_scanner: ChannelScanner | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global scheduler, channel_scanner

    # Debug: 打印当前运行中的 loop 类型
    _log_loop_type()

    # 1. Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. Seed default config + rule templates
    async with async_session_factory() as db:
        await seed_default_config(db)
        await db.commit()

    from app.services.scoring.rule_engine import seed_rule_templates
    await seed_rule_templates()

    # 3. Read config for scheduler
    from sqlalchemy import select
    from app.models.config import Config

    async with async_session_factory() as db:
        result = await db.execute(select(Config))
        configs = {c.key: c.value for c in result.scalars().all()}

    download_dir = configs.get("download_dir", "./downloads")
    max_concurrent = int(configs.get("max_concurrent_downloads", "3"))
    max_res = int(configs.get("max_resolution", "1080"))

    # 4. Start scheduler
    scheduler = TaskScheduler(
        download_dir=download_dir,
        max_concurrent=max_concurrent,
        max_resolution=max_res,
    )
    await scheduler.start()

    # 5. Phase 9: Start channel scanner (APScheduler)
    scan_max_concurrent = int(configs.get("scan_max_concurrent", "3"))
    scan_default_interval = int(configs.get("scan_default_interval_hours", "6"))
    channel_scanner = ChannelScanner(
        max_concurrent=scan_max_concurrent,
        default_interval_hours=scan_default_interval,
    )
    set_channel_scanner(channel_scanner)
    await channel_scanner.start()

    # 6. Phase 5 B3: Mount /static/downloads — serve dubbed audio/video preview files.
    # download_dir is relative to backend cwd; convert to absolute and ensure exists.
    static_dir = download_dir if os.path.isabs(download_dir) else os.path.abspath(download_dir)
    os.makedirs(static_dir, exist_ok=True)
    # Mount only if not already mounted (idempotent across reloads)
    existing_routes = {r.path for r in app.routes}
    if "/static/downloads/{path:path}" not in existing_routes:
        app.mount(
            "/static/downloads",
            StaticFiles(directory=static_dir),
            name="phase5_downloads_static",
        )

    yield

    # 7. Shutdown channel scanner
    if channel_scanner:
        await channel_scanner.stop()
        set_channel_scanner(None)

    # 8. Shutdown scheduler
    if scheduler:
        await scheduler.stop()

    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "phase": 5}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await ws_manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                # Parse incoming messages
                import json
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await ws_manager.send_personal({"type": "pong"}, websocket)
                except json.JSONDecodeError:
                    pass
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)

    return app


app = create_app()
