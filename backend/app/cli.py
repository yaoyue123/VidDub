"""Phase 4 CLI — python -m app.cli dub <youtube_url>

子命令：
- dub <url>     端到端配音：下载 → 转写 → 翻译 → 合成 → 拼接 → 输出 final.mp4
- status <id>   查询单个视频状态
- resume <id>   断点续跑 failed 视频

约束（per RESEARCH Q4 + 用户要求）：
- argparse 接口
- 进度通过 stdout 实时打印（WebSocket 非必需）
- SILICONFLOW_API_KEY 必须在 .env 设置，否则退出
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# 加载 .env（必须在 import app.core.config 前）
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from app.core.config import settings
from app.core.storage import get_download_dir

logger = logging.getLogger("cli")


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _check_env() -> None:
    """启动前检查必需的环境变量."""
    key = settings.siliconflow_api_key.strip()
    if not key:
        print("ERROR: SILICONFLOW_API_KEY 未设置。", file=sys.stderr)
        print("请复制 backend/.env.example 为 backend/.env 并填入密钥", file=sys.stderr)
        print("获取地址: https://cloud.siliconflow.cn/account/ak", file=sys.stderr)
        sys.exit(2)


def _print(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── 子命令实现 ──

async def _cmd_dub(args: argparse.Namespace) -> int:
    """端到端配音."""
    _check_env()

    from sqlalchemy import select
    from app.core.database import engine, Base, async_session_factory
    from app.models.video import Video
    from app.models.task import Task
    from app.models.enums import VideoStatus, TaskType, TaskStatus
    from app.services.config_seeder import seed_default_config
    from app.services.scheduler import TaskScheduler

    # 1. 建表 + seed config
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_factory() as db:
        await seed_default_config(db)
        await db.commit()

    # 2. 提取视频元数据
    from app.services.youtube import YoutubeService
    yt = YoutubeService()
    _print(f"获取视频信息: {args.youtube_url}")
    info = await yt.get_video_info(args.youtube_url)
    if not info:
        print(f"ERROR: 无法获取视频信息（URL 无效或网络问题）: {args.youtube_url}", file=sys.stderr)
        return 1
    _print(f"视频标题: {info.get('title')}  时长: {info.get('duration')}s")

    # 3. 创建 Video + download Task
    async with async_session_factory() as db:
        video = Video(
            youtube_url=args.youtube_url,
            youtube_id=info.get("youtube_id", args.youtube_url),
            title=info.get("title", "Untitled"),
            channel=info.get("channel", "Unknown"),
            duration=info.get("duration"),
            status=VideoStatus.PENDING,
        )
        db.add(video)
        await db.flush()
        await db.refresh(video)
        video_id = video.id

        task = Task(
            video_id=video_id,
            type=TaskType.DOWNLOAD,
            status=TaskStatus.PENDING,
            progress=0.0,
            message="等待下载...",
        )
        db.add(task)
        await db.commit()
        _print(f"Video 创建: id={video_id}, task_id={task.id}")

    # 4. 启动调度器
    sched = TaskScheduler(download_dir=get_download_dir(), max_concurrent=1)
    await sched.start()

    # 5. 轮询 DB 输出进度，直到 completed 或 failed
    try:
        last_step = ""
        while True:
            async with async_session_factory() as db:
                v = (await db.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
                t_result = await db.execute(
                    select(Task).where(Task.video_id == video_id)
                    .order_by(Task.created_at.desc()).limit(1)
                )
                latest_task = t_result.scalar_one_or_none()

            if not v:
                print("ERROR: Video 消失了", file=sys.stderr)
                return 1

            step = latest_task.type if latest_task else "?"
            progress = latest_task.progress if latest_task else 0
            msg = latest_task.message if latest_task else ""
            status = v.status

            if step != last_step or progress >= 99:
                _print(f"status={status} step={step} progress={progress:.1f}% {msg}")
                last_step = step
            else:
                # 每 10% 也打印
                if int(progress) % 10 == 0:
                    _print(f"status={status} step={step} progress={progress:.1f}% {msg}")

            if status == VideoStatus.COMPLETED:
                _print(f"✓ 完成! final.mp4: {v.dubbed_filepath}")
                work_dir = os.path.dirname(v.dubbed_filepath) if v.dubbed_filepath else ""
                if work_dir:
                    _print(f"  工作目录: {work_dir}")
                    _print(f"  字幕: {os.path.join(work_dir, 'subtitle.srt')}")
                return 0
            if status == VideoStatus.FAILED:
                err = latest_task.error_msg if latest_task else "unknown"
                print(f"ERROR: 任务失败: {err}", file=sys.stderr)
                print(f"  续跑: python -m app.cli resume {video_id}", file=sys.stderr)
                return 1

            await asyncio.sleep(2)
    except KeyboardInterrupt:
        _print("中断 — 任务仍在后台运行；可用 python -m app.cli status " + str(video_id) + " 查询")
        return 130
    finally:
        await sched.stop()
        await engine.dispose()


async def _cmd_status(args: argparse.Namespace) -> int:
    """查询单个视频状态."""
    from sqlalchemy import select
    from app.core.database import async_session_factory
    from app.models.video import Video
    from app.models.task import Task

    async with async_session_factory() as db:
        v = (await db.execute(select(Video).where(Video.id == args.video_id))).scalar_one_or_none()
        if not v:
            print(f"Video {args.video_id} not found", file=sys.stderr)
            return 1
        t_result = await db.execute(
            select(Task).where(Task.video_id == args.video_id)
            .order_by(Task.created_at.desc()).limit(1)
        )
        t = t_result.scalar_one_or_none()

    out = {
        "id": v.id,
        "youtube_url": v.youtube_url,
        "title": v.title,
        "status": v.status,
        "progress_pct": float(t.progress) if t else 0.0,
        "current_step": t.type if t else None,
        "message": t.message if t else None,
        "error_msg": t.error_msg if t else None,
        "final_path": v.dubbed_filepath,
        "created_at": str(v.created_at),
        "updated_at": str(v.updated_at),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


async def _cmd_resume(args: argparse.Namespace) -> int:
    """断点续跑 failed 视频."""
    from sqlalchemy import select, update
    from app.core.database import engine, async_session_factory
    from app.models.video import Video
    from app.models.task import Task
    from app.models.enums import VideoStatus, TaskStatus
    from app.services.scheduler import TaskScheduler

    async with async_session_factory() as db:
        v = (await db.execute(select(Video).where(Video.id == args.video_id))).scalar_one_or_none()
        if not v:
            print(f"Video {args.video_id} not found", file=sys.stderr)
            return 1
        if v.status != VideoStatus.FAILED:
            print(f"Video 状态非 failed (当前: {v.status})，无需续跑", file=sys.stderr)
            return 1

        t_result = await db.execute(
            select(Task).where(
                Task.video_id == args.video_id, Task.status == TaskStatus.FAILED
            ).order_by(Task.created_at.desc()).limit(1)
        )
        failed = t_result.scalar_one_or_none()
        if not failed:
            print("找不到 failed task", file=sys.stderr)
            return 1

        failed.status = TaskStatus.PENDING
        failed.progress = 0.0
        failed.error_msg = None
        failed.message = "等待重试..."
        # WR-02: 按 failed task 类型决定 Video 应恢复到的前驱状态（与 dub.py 一致）。
        from app.models.enums import TaskType
        _resume_status_map = {
            TaskType.DOWNLOAD: VideoStatus.PENDING,
            TaskType.TRANSCRIBE: VideoStatus.DOWNLOADED,
            TaskType.TRANSLATE: VideoStatus.TRANSCRIBED,
            TaskType.SYNTHESIZE: VideoStatus.TRANSLATED,
            TaskType.COMPOSE: VideoStatus.SYNTHESIZED,
        }
        new_video_status = _resume_status_map.get(failed.type, VideoStatus.FAILED)
        await db.execute(
            update(Video).where(Video.id == args.video_id).values(status=new_video_status)
        )
        await db.commit()
        _print(f"Task {failed.id} ({failed.type}) 已重置为 pending (video_status={new_video_status})")

    sched = TaskScheduler(download_dir=get_download_dir(), max_concurrent=1)
    await sched.start()
    try:
        last_step = ""
        while True:
            async with async_session_factory() as db:
                v = (await db.execute(select(Video).where(Video.id == args.video_id))).scalar_one_or_none()
                t_result = await db.execute(
                    select(Task).where(Task.video_id == args.video_id)
                    .order_by(Task.created_at.desc()).limit(1)
                )
                t = t_result.scalar_one_or_none()
            step = t.type if t else "?"
            progress = t.progress if t else 0
            msg = t.message if t else ""
            if step != last_step:
                _print(f"status={v.status} step={step} progress={progress:.1f}% {msg}")
                last_step = step

            if v.status == VideoStatus.COMPLETED:
                _print(f"✓ 续跑完成! final.mp4: {v.dubbed_filepath}")
                return 0
            if v.status == VideoStatus.FAILED:
                err = t.error_msg if t else "unknown"
                print(f"ERROR: 续跑再次失败: {err}", file=sys.stderr)
                return 1
            await asyncio.sleep(2)
    except KeyboardInterrupt:
        _print("中断 — 后台仍运行")
        return 130
    finally:
        await sched.stop()
        await engine.dispose()


# ── argparse entry ──

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="viddub 端到端配音 CLI (Phase 4)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_dub = sub.add_parser("dub", help="端到端配音：YouTube URL → 中文配音 mp4")
    p_dub.add_argument("youtube_url", help="YouTube 视频 URL")
    p_dub.add_argument("--verbose", action="store_true", help="详细日志")

    p_status = sub.add_parser("status", help="查询单个视频状态")
    p_status.add_argument("video_id", type=int)

    p_resume = sub.add_parser("resume", help="断点续跑 failed 视频")
    p_resume.add_argument("video_id", type=int)
    p_resume.add_argument("--verbose", action="store_true")

    args = parser.parse_args()
    _setup_logging(getattr(args, "verbose", False))

    if args.command == "dub":
        return asyncio.run(_cmd_dub(args))
    elif args.command == "status":
        return asyncio.run(_cmd_status(args))
    elif args.command == "resume":
        return asyncio.run(_cmd_resume(args))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
