"""
Subtitle API: list, save, download subtitles, retranslate single segment.

Phase 5 新增：
- POST /api/subtitles/{video_id}/retranslate?segment_index=N — 重新翻译单段 (B2, D5-06)
"""
import json
import os
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.storage import get_download_dir
from app.models.subtitle import Subtitle
from app.models.video import Video
from app.models.config import Config

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──

class SubtitleResponse(BaseModel):
    id: int
    video_id: int
    language: str
    source: str
    content: Optional[str] = None
    filepath: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


class SubtitleListResponse(BaseModel):
    total: int
    items: list[SubtitleResponse]


class SubtitleSaveRequest(BaseModel):
    content: str = Field(..., description="SRT or JSON subtitle content")
    language: str = Field(default="zh", description="Language code")
    source: str = Field(default="manual", description="whisper / manual / translation")


# ── Routes ──

@router.get("/{video_id}", response_model=SubtitleListResponse)
async def list_subtitles(
    video_id: int,
    db: AsyncSession = Depends(get_db),
):
    """List all subtitle entries for a video."""
    # Verify video exists
    v_result = await db.execute(select(Video).where(Video.id == video_id))
    if not v_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Video not found")

    result = await db.execute(
        select(Subtitle)
        .where(Subtitle.video_id == video_id)
        .order_by(Subtitle.language)
    )
    items = result.scalars().all()

    count_result = await db.execute(
        select(func.count(Subtitle.id)).where(Subtitle.video_id == video_id)
    )
    total = count_result.scalar() or 0

    return SubtitleListResponse(total=total, items=list(items))


@router.post("/{video_id}", response_model=SubtitleResponse, status_code=201)
async def save_subtitle(
    video_id: int,
    body: SubtitleSaveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Save or update subtitle content for a video."""
    # Verify video
    v_result = await db.execute(select(Video).where(Video.id == video_id))
    if not v_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Video not found")

    # Check for existing subtitle for this language + source
    existing_result = await db.execute(
        select(Subtitle).where(
            Subtitle.video_id == video_id,
            Subtitle.language == body.language,
            Subtitle.source == body.source,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.content = body.content
        existing.source = body.source
        subtitle = existing
    else:
        subtitle = Subtitle(
            video_id=video_id,
            language=body.language,
            source=body.source,
            content=body.content,
        )
        db.add(subtitle)

    await db.flush()
    await db.refresh(subtitle)
    return subtitle


@router.get("/{video_id}/download/{language}")
async def download_subtitle(
    video_id: int,
    language: str,
    fmt: str = "srt",
    db: AsyncSession = Depends(get_db),
):
    """Download subtitle file for a video/language pair."""
    result = await db.execute(
        select(Subtitle).where(
            Subtitle.video_id == video_id,
            Subtitle.language == language,
        ).order_by(Subtitle.updated_at.desc())
    )
    subtitle = result.scalar_one_or_none()
    if not subtitle:
        raise HTTPException(status_code=404, detail="Subtitle not found")

    # If file exists on disk, serve it
    if subtitle.filepath and os.path.exists(subtitle.filepath):
        media_type = "text/vtt" if fmt == "vtt" else "application/x-subrip"
        return FileResponse(subtitle.filepath, media_type=media_type)

    # Fall back to content from DB
    if not subtitle.content:
        raise HTTPException(status_code=404, detail="Subtitle content is empty")

    content_type = "text/vtt" if fmt == "vtt" else "text/plain; charset=utf-8"
    filename = f"subtitle_{video_id}_{language}.{fmt}"

    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=subtitle.content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Phase 5: B2 重新翻译单段 (D5-06) ──

class RetranslateResponse(BaseModel):
    """单段重新翻译结果."""
    segment_index: int
    original_text: str
    translated_text: str
    updated_files: list[str]


def _resolve_download_dir(db_configs: dict[str, str]) -> str:
    return get_download_dir()


def _load_translated_json(video_dir: str) -> list[dict]:
    """读取 downloads/{video_id}/translated.json — 翻译管线产物."""
    path = os.path.join(video_dir, "translated.json")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail=f"translated.json 未找到 ({path})。请先完整跑一次 Phase 4 管线。",
        )
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(
            status_code=500,
            detail=f"读取 translated.json 失败: {e}",
        )
    if not isinstance(data, list):
        raise HTTPException(
            status_code=500,
            detail="translated.json 不是数组格式",
        )
    return data


def _write_translated_json(video_dir: str, data: list[dict]) -> None:
    path = os.path.join(video_dir, "translated.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _seconds_to_srt_time(s: float) -> str:
    """把秒数转成 SRT 时间戳 HH:MM:SS,mmm."""
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


def _regenerate_srt(video_dir: str, data: list[dict]) -> None:
    """根据 translated segments 重新生成 subtitle.srt (中文)."""
    lines: list[str] = []
    for i, seg in enumerate(data, start=1):
        start = _seconds_to_srt_time(float(seg.get("start", 0)))
        end = _seconds_to_srt_time(float(seg.get("end", 0)))
        text = str(seg.get("text_zh", seg.get("text", ""))).strip()
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    srt_path = os.path.join(video_dir, "subtitle.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


@router.post(
    "/{video_id}/retranslate",
    response_model=RetranslateResponse,
    operation_id="retranslate_segment",
)
async def retranslate_segment(
    video_id: int,
    segment_index: int,
    db: AsyncSession = Depends(get_db),
):
    """重新翻译单段中文 (B2, D5-06).

    读取 downloads/{video_id}/translated.json → 调用 SiliconFlow Chat 翻译
    该段的 text (原文) → 写回 translated.json + 重新生成 subtitle.srt。
    """
    # 1. 校验 video
    v_result = await db.execute(select(Video).where(Video.id == video_id))
    video = v_result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # 2. 读 download_dir 配置 + translated.json
    cfg_result = await db.execute(select(Config))
    db_configs = {c.key: c.value for c in cfg_result.scalars().all()}
    download_dir = _resolve_download_dir(db_configs)
    video_dir = os.path.join(download_dir, str(video_id))
    data = _load_translated_json(video_dir)

    if segment_index < 0 or segment_index >= len(data):
        raise HTTPException(
            status_code=422,
            detail=f"segment_index 越界: 0-{len(data) - 1}, 收到 {segment_index}",
        )

    seg = data[segment_index]
    original_text = str(seg.get("text", "")).strip()
    if not original_text:
        raise HTTPException(
            status_code=422,
            detail=f"段 {segment_index} 原文为空，无法翻译",
        )

    # 3. 调用 SiliconFlow Chat 翻译
    # 使用 Phase 4 的 siliconflow.translate.translate_text (单段)
    try:
        from app.services.siliconflow.client import get_async_client
        from app.services.siliconflow.translate import translate_text

        translate_model = db_configs.get("translation_model", "deepseek-ai/DeepSeek-V4-Flash")
        async with get_async_client(timeout=30.0) as client:
            translated_text = await translate_text(
                client,
                original_text,
                model=translate_model,
                source_lang="English",
                target_lang="Chinese",
            )
        translated_text = (translated_text or "").strip().strip('"').strip("'")
        if not translated_text:
            raise RuntimeError("翻译返回空内容")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("retranslate failed for video=%s seg=%s", video_id, segment_index)
        raise HTTPException(
            status_code=502,
            detail=f"SiliconFlow 翻译失败: {e}",
        )

    # 4. 写回 translated.json + 重新生成 SRT
    seg["text_zh"] = translated_text
    # 兼容字段：若旧字段是 text（同时存中英文），也更新 zh 字段
    data[segment_index] = seg
    _write_translated_json(video_dir, data)
    updated_files = [os.path.join(video_dir, "translated.json")]

    try:
        _regenerate_srt(video_dir, data)
        updated_files.append(os.path.join(video_dir, "subtitle.srt"))
    except Exception as e:
        logger.warning("regenerate subtitle.srt failed: %s", e)

    return RetranslateResponse(
        segment_index=segment_index,
        original_text=original_text,
        translated_text=translated_text,
        updated_files=updated_files,
    )
