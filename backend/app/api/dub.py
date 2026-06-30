"""Phase 4 端到端配音 API.

POST /api/dub           — 创建新配音任务（输入 youtube_url）
GET  /api/dub/{id}      — 查询状态/进度
GET  /api/dub/{id}/download  — 下载 final.mp4
GET  /api/dub/{id}/subtitle  — 获取 SRT 文本
POST /api/dub/{id}/resume   — 失败任务断点续跑

注意：调度器在 main.py lifespan 启动后会自动 polling pending tasks，
所以 POST /api/dub 只需创建 Video + download Task 即可触发整个 chain。
"""
import logging
import os
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.storage import get_download_dir
from app.models.video import Video
from app.models.task import Task
from app.models.config import Config
from app.models.enums import VideoStatus, TaskType, TaskStatus

logger = logging.getLogger(__name__)
router = APIRouter()


# CR-03: SSRF 防护 — youtube_url 只允许 YouTube 主域名，否则 yt-dlp 会被滥用做内网探测。
YOUTUBE_HOSTS = frozenset({
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
})


def _validate_youtube_url(url: str) -> None:
    """校验 youtube_url 是否指向 YouTube 主域名（防 SSRF）."""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=422,
            detail="youtube_url 必须是 http(s):// 开头",
        )
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=422,
            detail=f"不支持的 URL scheme: {parsed.scheme!r}",
        )
    host = (parsed.hostname or "").lower()
    if not host:
        raise HTTPException(
            status_code=422,
            detail="youtube_url 缺少 hostname",
        )
    if host not in YOUTUBE_HOSTS:
        raise HTTPException(
            status_code=422,
            detail=f"URL 必须指向 YouTube (允许: {sorted(YOUTUBE_HOSTS)})，"
                   f"当前 host: {host!r}",
        )


# ── Schemas ──

class DubCreateRequest(BaseModel):
    youtube_url: str = Field(..., description="YouTube 视频 URL")


class DubCreateResponse(BaseModel):
    video_id: int
    status: str
    task_id: int


class DubStatusResponse(BaseModel):
    id: int
    youtube_url: str
    title: str
    status: str
    progress_pct: float
    current_step: str
    error_msg: str | None = None
    final_url: str | None = None
    srt_url: str | None = None
    created_at: str
    updated_at: str


# ── Endpoints ──

@router.post("", response_model=DubCreateResponse, status_code=201)
async def create_dub(
    body: DubCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """创建一个新配音任务 — 自动提取视频信息并触发 download → ... → compose chain."""
    url = str(body.youtube_url).strip()
    _validate_youtube_url(url)  # CR-03: SSRF 防护 — 只允许 YouTube 主域名

    # 提取 youtube_id（先用 yt-dlp 抓 metadata；失败则用 url hash 兜底）
    from app.services.youtube import YoutubeService
    yt = YoutubeService()
    try:
        info = await yt.get_video_info(url)
    except Exception as e:
        logger.warning("get_video_info failed: %s — using placeholder metadata", e)
        info = None

    if info:
        youtube_id = info.get("youtube_id") or url
        title = info.get("title") or "Untitled"
        channel = info.get("channel") or "Unknown"
        duration = info.get("duration")
        thumbnail_url = info.get("thumbnail_url")
    else:
        youtube_id = url  # 兜底
        title = "Untitled"
        channel = "Unknown"
        duration = None
        thumbnail_url = None

    # 创建 Video
    video = Video(
        youtube_url=url,
        youtube_id=youtube_id,
        title=title,
        channel=channel,
        duration=duration,
        thumbnail_url=thumbnail_url,
        status=VideoStatus.PENDING,
    )
    db.add(video)
    await db.flush()
    await db.refresh(video)

    # 创建首个 download Task
    task = Task(
        video_id=video.id,
        type=TaskType.DOWNLOAD,
        status=TaskStatus.PENDING,
        progress=0.0,
        message="等待下载...",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    return DubCreateResponse(
        video_id=video.id, status=VideoStatus.PENDING, task_id=task.id,
    )


@router.get("/{video_id}", response_model=DubStatusResponse)
async def get_dub_status(
    video_id: int,
    db: AsyncSession = Depends(get_db),
):
    """查询配音进度."""
    v = (await db.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, detail="Video not found")

    # 最新 task
    t_result = await db.execute(
        select(Task).where(Task.video_id == video_id)
        .order_by(Task.created_at.desc()).limit(1)
    )
    latest_task = t_result.scalar_one_or_none()

    progress_pct = float(latest_task.progress) if latest_task else 0.0
    current_step = latest_task.type if latest_task else "idle"
    error_msg = latest_task.error_msg if latest_task else None

    # 读取 download_dir 配置
    download_dir = get_download_dir()

    final_url = None
    srt_url = None
    if v.status == VideoStatus.COMPLETED:
        final_url = f"/api/dub/{video_id}/download"
        srt_url = f"/api/dub/{video_id}/subtitle"

    return DubStatusResponse(
        id=v.id,
        youtube_url=v.youtube_url,
        title=v.title,
        status=v.status,
        progress_pct=progress_pct,
        current_step=current_step,
        error_msg=error_msg,
        final_url=final_url,
        srt_url=srt_url,
        created_at=str(v.created_at),
        updated_at=str(v.updated_at),
    )


@router.get("/{video_id}/download")
async def download_dubbed_video(
    video_id: int,
    db: AsyncSession = Depends(get_db),
):
    """下载 final.mp4."""
    v = (await db.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, detail="Video not found")
    if v.status != VideoStatus.COMPLETED:
        raise HTTPException(409, detail=f"Video not ready (status={v.status})")

    # 找 final.mp4 路径
    final_path = v.dubbed_filepath
    if not final_path or not os.path.exists(final_path):
        # 兜底：按约定路径找
        download_dir = get_download_dir()
        final_path = os.path.join(download_dir, str(video_id), "final.mp4")
        if not os.path.exists(final_path):
            raise HTTPException(404, detail="final.mp4 not found on disk")

    return FileResponse(final_path, media_type="video/mp4", filename=f"video_{video_id}_dubbed.mp4")


@router.get("/{video_id}/subtitle", response_class=PlainTextResponse)
async def get_subtitle(
    video_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取中文 SRT 字幕."""
    v = (await db.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, detail="Video not found")

    work_dir = os.path.join(get_download_dir(), str(video_id))
    if not os.path.isdir(work_dir):
        logger.warning("work dir not found for video %s at %s", video_id, work_dir)
        return ""

    # Load transcript for English text with timestamps
    import json
    transcript_path = os.path.join(work_dir, "transcript.json")
    transcript_segments: list[dict] = []
    if os.path.exists(transcript_path):
        try:
            t = json.load(open(transcript_path, "r", encoding="utf-8"))
            if isinstance(t, list):
                transcript_segments = t
        except Exception:
            logger.warning("failed to parse transcript.json for video %s", video_id, exc_info=True)

    # Find English text for a given time range by matching overlapping transcript segments
    def _find_en(start: float, end: float) -> str:
        parts: list[str] = []
        for ts in transcript_segments:
            ts_start = float(ts.get("start", 0))
            ts_end = float(ts.get("end", 0))
            # Overlap if segment starts before our end AND ends after our start
            if ts_start < end and ts_end > start:
                text = (ts.get("text", "") or "").strip()
                if text:
                    parts.append(text)
        return " ".join(parts) if parts else ""

    # Try loading the actual SRT file first (Chinese text with correct timing)
    srt_content = ""
    try:
        for f in os.listdir(work_dir):
            if f.endswith(".srt"):
                srt_path = os.path.join(work_dir, f)
                with open(srt_path, "r", encoding="utf-8") as fh:
                    srt_content = fh.read().strip()
                if srt_content:
                    break
    except OSError:
        pass

    if srt_content:
        # Parse SRT, then merge with English from transcript
        lines: list[str] = []
        for block in srt_content.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            blines = block.split("\n")
            if len(blines) < 2:
                continue
            idx = 0
            if blines[0].strip().isdigit():
                idx = 1
            # Parse time: "00:00:00,000 --> 00:00:03,500"
            tm_match = blines[idx].strip() if idx < len(blines) else ""
            import re as _re
            tm = _re.match(r"([\d:,]+)\s*-->\s*([\d:,]+)", tm_match)
            if not tm:
                continue
            start = _srt2sec(tm.group(1))
            end = _srt2sec(tm.group(2))
            text_zh = "\n".join(blines[idx + 1:]).strip() if idx + 1 < len(blines) else ""
            text_en = _find_en(start, end)
            idx_num = len(lines) // 4 + 1
            text = f"{text_en}\n{text_zh}" if text_en and text_zh else (text_zh or text_en)
            lines.append(str(idx_num))
            lines.append(f"{_sec2srt(start)} --> {_sec2srt(end)}")
            lines.append(text)
            lines.append("")
        if lines:
            return "\n".join(lines)

    # Fallback: find any .srt file in the work dir
    try:
        for f in os.listdir(work_dir):
            if f.endswith(".srt"):
                srt_path = os.path.join(work_dir, f)
                with open(srt_path, "r", encoding="utf-8") as fh:
                    content = fh.read().strip()
                if content:
                    return content
    except OSError:
        pass

    logger.warning("no subtitle found for video %s in %s", video_id, work_dir)
    return ""


def _sec2srt(s: float) -> str:
    """Convert seconds to SRT time format HH:MM:SS,mmm."""
    if s < 0:
        s = 0
    ms = int(round((s - int(s)) * 1000))
    if ms >= 1000:
        s += 1
        ms -= 1000
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def _srt2sec(t: str) -> float:
    """Convert SRT time string (HH:MM:SS,mmm) to seconds."""
    import re as _re
    m = _re.match(r"(\d+):(\d+):(\d+)[,.](\d+)", t.strip())
    if not m:
        return 0.0
    h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    return float(h * 3600 + mi * 60 + s + ms / 1000.0)


@router.post("/{video_id}/resume")
async def resume_dubbing(
    video_id: int,
    db: AsyncSession = Depends(get_db),
):
    """断点续跑 — 把最近一个 failed Task 重置为 pending."""
    v = (await db.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, detail="Video not found")
    if v.status != VideoStatus.FAILED:
        raise HTTPException(400, detail=f"Video not in failed state (current: {v.status})")

    # 找最近 failed task
    t_result = await db.execute(
        select(Task).where(
            Task.video_id == video_id, Task.status == TaskStatus.FAILED
        ).order_by(Task.created_at.desc()).limit(1)
    )
    failed_task = t_result.scalar_one_or_none()
    if not failed_task:
        raise HTTPException(400, detail="No failed task to resume")

    failed_task.status = TaskStatus.PENDING
    failed_task.progress = 0.0
    failed_task.error_msg = None
    failed_task.message = "等待重试..."

    # WR-02: 不再无条件重置为 DOWNLOADED — 那会让 compose 失败的视频从 transcribe
    # 重新跑（Whisper 全片重转，浪费工时）。改为按 failed task 类型把 Video 状态
    # 退回到该阶段对应的"前驱"状态：该阶段尚未完成 → 前驱状态是上游阶段的"完成态"。
    # 不存在的任务类型则保守地保留原 FAILED 状态（让运维介入）。
    _resume_status_map = {
        TaskType.DOWNLOAD: VideoStatus.PENDING,
        TaskType.TRANSCRIBE: VideoStatus.DOWNLOADED,
        TaskType.TRANSLATE: VideoStatus.TRANSCRIBED,
        TaskType.SYNTHESIZE: VideoStatus.TRANSLATED,
        TaskType.COMPOSE: VideoStatus.SYNTHESIZED,
    }
    new_video_status = _resume_status_map.get(failed_task.type, VideoStatus.FAILED)
    await db.execute(
        update(Video).where(Video.id == video_id).values(status=new_video_status)
    )
    await db.flush()

    return {
        "video_id": video_id,
        "resumed_task_id": failed_task.id,
        "resumed_task_type": failed_task.type,
        "status": TaskStatus.PENDING,
        "video_status": new_video_status,
    }


# ── Phase 5: B4 预览配音 / 成片 / 原视频 (D5-02) ──

_PREVIEW_KINDS = ("dubbing", "final", "original")

# kind → file name 在 downloads/{video_id}/ 下的映射
_PREVIEW_FILENAMES = {
    "dubbing": "dubbing.wav",   # 中文 TTS 合成的配音 (Phase 4 stitcher 产物)
    "final": "final.mp4",       # 默认名；运行时优先从 DB 解析实际文件名
    "original": "original.mp4", # 原视频（download 阶段产物）
}

# kind → HTTP content-type
_PREVIEW_CONTENT_TYPES = {
    "dubbing": "audio/wav",
    "final": "video/mp4",
    "original": "video/mp4",
}


def _resolve_final_filename(video, work_dir: str) -> str:
    """Resolve the actual final.mp4 filename for a video.

    The composer uses sanitize_filename(video.title_zh or title) as the
    output stem (e.g. ``AI_MKBHD_评测.mp4``), not a hardcoded "final.mp4".
    This function finds the actual file so the preview endpoint returns
    the correct FileResponse.
    """
    from app.services.dubbing.paths import sanitize_filename

    # 1) Try the DB-resolved stem
    candidate = (video.title_chosen or video.title_zh or video.title or "").strip()
    if candidate:
        stem = sanitize_filename(candidate) or f"video_{video.id}"
        path = os.path.join(work_dir, f"{stem}.mp4")
        if os.path.exists(path):
            return os.path.basename(path)

    # 2) Try "final.mp4" (legacy / fallback)
    fallback = os.path.join(work_dir, "final.mp4")
    if os.path.exists(fallback):
        return "final.mp4"

    # 3) Try any .mp4 that isn't original / _subtitled
    try:
        for f in os.listdir(work_dir):
            if f.endswith(".mp4") and f not in ("original.mp4",) and "_subtitled" not in f:
                return f
    except OSError:
        pass

    # 4) Default — will 404 with a clear message
    return "final.mp4"


@router.get("/{video_id}/preview/{kind}")
async def preview_dub_artifact(
    video_id: int,
    kind: str,
    db: AsyncSession = Depends(get_db),
):
    """预览配音/成片/原视频文件 (B4, D5-02).

    kind:
      - dubbing:   downloads/{id}/dubbing.wav (中文 TTS 配音)
      - final:     downloads/{id}/final.mp4   (最终合成视频)
      - original:  downloads/{id}/original.mp4 (原视频)

    返回 FileResponse，浏览器内置 <audio>/<video> 可直接播放。
    """
    if kind not in _PREVIEW_KINDS:
        raise HTTPException(
            status_code=422,
            detail=f"kind 必须是 {_PREVIEW_KINDS}，收到 {kind!r}",
        )

    v = (await db.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, detail="Video not found")

    download_dir = get_download_dir()
    work_dir = os.path.join(download_dir, str(video_id))

    filename = _PREVIEW_FILENAMES[kind]
    # For "final" kind: resolve actual filename from DB (composer uses video title)
    if kind == "final":
        filename = _resolve_final_filename(v, work_dir)

    path = os.path.join(work_dir, filename)

    if not os.path.exists(path):
        # 兜底：dubbing.wav 不存在时尝试 dubbing.mp3
        if kind == "dubbing":
            alt = os.path.join(work_dir, "dubbing.mp3")
            if os.path.exists(alt):
                return FileResponse(alt, media_type="audio/mpeg")
        raise HTTPException(
            status_code=404,
            detail=f"{filename} 还未生成 (video_id={video_id}, kind={kind})",
        )

    return FileResponse(path, media_type=_PREVIEW_CONTENT_TYPES[kind])
