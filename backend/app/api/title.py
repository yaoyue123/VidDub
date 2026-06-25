"""Phase 8: AI 智能标题与标签 API.

路由：
- POST  /api/title/{video_id}/generate   触发生成候选（5 标题 + 8 标签）
- GET   /api/title/{video_id}            返回已保存的候选 + 用户选择
- PUT   /api/title/{video_id}            保存用户选择（title_chosen + tags_chosen）

设计：
- POST generate 内部调 title_generator.generate_title_candidates
- GET / PUT 直接读写 videos 表的新增列
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, async_session_factory
from app.models.config import Config
from app.models.video import Video
from app.services.title_generator import generate_title_candidates

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──

class TitleCandidate(BaseModel):
    """单条候选（前端展示用，无独立 DB 表）."""
    title: str


class GenerateResponse(BaseModel):
    video_id: int
    titles: list[str]
    tags: list[str]
    summary_zh: str = ""
    cached: bool = False  # 是否返回了已缓存的候选（未触发 API）


class SaveBody(BaseModel):
    """PUT /api/title/{video_id} 请求体."""
    title_chosen: Optional[str] = Field(None, max_length=200)
    tags_chosen: Optional[list[str]] = Field(None)


class SavedState(BaseModel):
    """GET /api/title/{video_id} 返回结构."""
    video_id: int
    ai_title_candidates: list[str] = []
    ai_tags_candidates: list[str] = []
    title_chosen: Optional[str] = None
    tags_chosen: list[str] = []


# ── Helpers ──

def _parse_json_array(raw: Optional[str]) -> list[str]:
    """容忍 null / 非 JSON / 非 array 的 JSON 数组解析."""
    if not raw:
        return []
    try:
        v = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if x is not None and str(x).strip()]


def _dump_json_array(items: Optional[list[str]]) -> Optional[str]:
    if items is None:
        return None
    return json.dumps([str(t) for t in items], ensure_ascii=False)


async def _load_configs(db: AsyncSession) -> dict[str, str]:
    """从 Config 表读所有键值."""
    result = await db.execute(select(Config))
    return {c.key: c.value for c in result.scalars().all()}


async def _get_video_or_404(db: AsyncSession, video_id: int) -> Video:
    v = (await db.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, detail=f"video {video_id} not found")
    return v


# ── Endpoints ──

@router.post("/{video_id}/generate", response_model=GenerateResponse)
async def trigger_generate(video_id: int, db: AsyncSession = Depends(get_db)):
    """触发生成 5 标题 + 8 标签候选 (调 SiliconFlow Chat JSON mode).

    成功后写入 videos.ai_title_candidates / ai_tags_candidates；
    失败返回 200 + 空 arrays，让前端降级显示。
    """
    v = await _get_video_or_404(db, video_id)
    configs = await _load_configs(db)

    enabled = configs.get("title_generator_enabled", "true").lower() in ("true", "1", "yes")
    if not enabled:
        raise HTTPException(409, detail="AI 标题生成已被关闭 (title_generator_enabled=false)")

    try:
        result = await generate_title_candidates(
            v,
            configs=configs,
            num_titles=int(configs.get("title_generator_candidate_count", "5")),
            num_tags=int(configs.get("title_generator_tag_count", "8")),
        )
    except Exception as e:
        logger.error("title generation failed for video %d: %s", video_id, e, exc_info=True)
        return GenerateResponse(video_id=video_id, titles=[], tags=[], summary_zh="", cached=False)

    # 写回 DB（即使部分为空也覆盖，避免上次缓存误导）
    await db.execute(
        update(Video).where(Video.id == video_id).values(
            ai_title_candidates=_dump_json_array(result["titles"]),
            ai_tags_candidates=_dump_json_array(result["tags"]),
        )
    )
    await db.commit()

    return GenerateResponse(
        video_id=video_id,
        titles=result["titles"],
        tags=result["tags"],
        summary_zh=result["summary_zh"],
        cached=False,
    )


@router.get("/{video_id}", response_model=SavedState)
async def get_saved(video_id: int, db: AsyncSession = Depends(get_db)):
    """读取已保存的候选 + 用户已选."""
    v = await _get_video_or_404(db, video_id)
    return SavedState(
        video_id=video_id,
        ai_title_candidates=_parse_json_array(v.ai_title_candidates),
        ai_tags_candidates=_parse_json_array(v.ai_tags_candidates),
        title_chosen=v.title_chosen,
        tags_chosen=_parse_json_array(v.tags_chosen),
    )


@router.put("/{video_id}", response_model=SavedState)
async def save_choice(video_id: int, body: SaveBody, db: AsyncSession = Depends(get_db)):
    """保存用户选择的 title_chosen / tags_chosen."""
    v = await _get_video_or_404(db, video_id)

    update_values: dict[str, Any] = {}
    if body.title_chosen is not None:
        title = body.title_chosen.strip()
        if not title:
            raise HTTPException(400, detail="title_chosen 不能为空字符串")
        update_values["title_chosen"] = title[:200]
    if body.tags_chosen is not None:
        # 限制 ≤ 12 个标签（Bilibili 上限 10，留余地）
        clean_tags = [t.strip() for t in body.tags_chosen if t and t.strip()][:12]
        update_values["tags_chosen"] = _dump_json_array(clean_tags)

    if update_values:
        await db.execute(update(Video).where(Video.id == video_id).values(**update_values))
        await db.commit()
        await db.refresh(v)

    return SavedState(
        video_id=video_id,
        ai_title_candidates=_parse_json_array(v.ai_title_candidates),
        ai_tags_candidates=_parse_json_array(v.ai_tags_candidates),
        title_chosen=v.title_chosen,
        tags_chosen=_parse_json_array(v.tags_chosen),
    )
