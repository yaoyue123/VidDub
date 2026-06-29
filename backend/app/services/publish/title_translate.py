"""Title/description translation helper (Phase 7, B9, D7-03).

使用 SiliconFlow Chat 把原 YouTube 视频标题/描述翻译为中文，
标签 = 原 tags 翻译 + 默认标签 (["搬运", "英语学习", "翻译"])，
为后续 publisher 提供填表字段。

Phase 8 完成后会被 AI 智能标题/标签替换。
"""
from __future__ import annotations

import logging
from typing import Optional

from app.services.publish.base import PublishFields

logger = logging.getLogger(__name__)


# 默认标签 (D7-03)
DEFAULT_TAGS = ["搬运", "英语学习", "翻译"]


async def prepare_publish_fields(video_id: int) -> PublishFields:
    """根据 video_id 拉取视频信息 + 调 SiliconFlow Chat 生成中文标题/描述/标签.

    流程（Phase 8 更新）：
    1. 从 DB 取 Video (title/description + Phase 8 新增字段)
    2. 若用户已选 title_chosen / tags_chosen → 直接使用（不再调 API）
    3. 否则调 SiliconFlow Chat 翻译（Phase 7 fallback）
    4. 拉配置：bilibili_default_category / ixigua_default_copyright / publish_default_tags
    5. 返回 PublishFields (默认转载 + 来源原 YouTube URL)
    """
    import json as _json
    from sqlalchemy import select
    from app.core.database import async_session_factory
    from app.models.config import Config
    from app.models.video import Video

    async with async_session_factory() as session:
        v = (await session.execute(
            select(Video).where(Video.id == video_id)
        )).scalar_one_or_none()
        if not v:
            raise ValueError(f"video {video_id} not found")

        cfg_result = await session.execute(select(Config))
        configs = {c.key: c.value for c in cfg_result.scalars().all()}

    title_en = v.title or f"video-{video_id}"
    desc_en = v.description or ""

    # ── Phase 8: 若用户已选标题/标签，优先使用 (D8-10) ──
    title_chosen = getattr(v, "title_chosen", None)
    tags_chosen_raw = getattr(v, "tags_chosen", None)
    tags_chosen: list[str] = []
    if tags_chosen_raw:
        try:
            parsed = _json.loads(tags_chosen_raw)
            if isinstance(parsed, list):
                tags_chosen = [str(t).strip() for t in parsed if t and str(t).strip()]
        except (ValueError, TypeError):
            tags_chosen = []

    if title_chosen:
        logger.info("Phase 8: using user-chosen title for video %d", video_id)
        title_zh = title_chosen
        desc_zh = desc_en
        # 用户已选标签 + 默认标签组合
        tags_zh = list(tags_chosen)
    elif tags_chosen:
        # 标题未选但标签已选 → 仅用标签部分
        title_zh = None  # 触发下面的翻译
        tags_zh = list(tags_chosen)
    else:
        title_zh = None
        tags_zh = []

    # ── 标题/描述 fallback：调 SiliconFlow 翻译 ──
    if title_zh is None:
        try:
            translated_title, desc_zh, translated_tags = await _translate_via_siliconflow(
                title_en, desc_en, configs
            )
        except Exception as e:
            logger.warning("SiliconFlow translate failed (%s), falling back", e)
            translated_title = title_en
            desc_zh = desc_en
            translated_tags = []
        title_zh = translated_title
        # 标签：用户已选优先 + 翻译补充
        if not tags_zh:
            tags_zh = translated_tags

    # 组合默认标签
    default_tags_csv = configs.get("publish_default_tags", "搬运,英语学习,翻译")
    default_tags = [t.strip() for t in default_tags_csv.split(",") if t.strip()]
    combined_tags = list(dict.fromkeys(tags_zh + default_tags))[:10]

    # 配置项
    category_id = configs.get("bilibili_default_category", "122")
    cover_path = _find_thumbnail_path(video_id, v.thumbnail_url)

    return PublishFields(
        title=title_zh[:80],
        description=desc_zh,
        tags=combined_tags,
        cover_path=cover_path,
        category_id=category_id,
        copyright_type="repost",
        source_url=v.youtube_url,
    )


async def _translate_via_siliconflow(
    title_en: str, desc_en: str, configs: dict[str, str]
) -> tuple[str, str, list[str]]:
    """调用 SiliconFlow Chat，把英文标题/描述翻译为中文，并提取关键词作为标签."""
    from app.services.siliconflow.client import get_async_client

    model = configs.get("translation_model", "deepseek-ai/DeepSeek-V4-Flash")

    prompt = (
        "你是专业的视频标题翻译。请把下面英文视频的标题和描述翻译成符合中文互联网风格的"
        "爆款标题和描述。标题简洁吸引人，描述简洁概括。"
        "另外从翻译内容中提取 3-5 个中文标签（用逗号分隔），"
        "标签应该是该视频最容易在中文平台被搜索到的关键词。\n\n"
        f"英文标题：{title_en}\n\n"
        f"英文描述：{desc_en[:500]}\n\n"
        "请严格按以下 JSON 格式返回（不要任何额外文字、不要 markdown 代码块）：\n"
        '{"title":"中文标题","description":"中文描述","tags":["标签1","标签2","标签3"]}'
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个专业的视频内容本地化助手。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 600,
    }

    async with get_async_client(timeout=30.0) as client:
        from app.services.siliconflow.client import sf_post
        resp = await sf_post(client, "chat/completions", json=payload)
        data = resp.json()

    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    title, desc, tags = _parse_translate_response(content)
    if not title:
        title = title_en
    return title, desc, tags


def _parse_translate_response(content: str) -> tuple[str, str, list[str]]:
    """解析 SiliconFlow 返回的 JSON (容忍 markdown code fence)."""
    import json
    import re

    s = content.strip()
    # 去掉 markdown 代码块
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    # 尝试找到最外层 { } 块
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        s = m.group(0)
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return "", "", []

    title = (obj.get("title") or "").strip()
    desc = (obj.get("description") or "").strip()
    raw_tags = obj.get("tags") or []
    if isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    elif isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    else:
        tags = []
    return title, desc, tags


def _find_thumbnail_path(video_id: int, thumbnail_url: Optional[str]) -> Optional[str]:
    """尝试在 downloads/{video_id}/ 目录找到本地封面图文件."""
    import os
    candidates = [
        os.path.join("downloads", str(video_id), "thumbnail.jpg"),
        os.path.join("downloads", str(video_id), "thumbnail.png"),
        os.path.join("downloads", str(video_id), "cover.jpg"),
        os.path.join("backend", "downloads", str(video_id), "thumbnail.jpg"),
        os.path.join("backend", "downloads", str(video_id), "cover.jpg"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return os.path.abspath(p)
    return None
