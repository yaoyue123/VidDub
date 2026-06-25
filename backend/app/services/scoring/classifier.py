"""Content category classifier via SiliconFlow Chat API.

Classifies videos into categories used by the scoring engine.
Results are cached per channel (channels rarely change category).
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Category list (must match BILIBILI_MARKET_FIT keys in scorer.py)
CATEGORIES = [
    "tech", "education", "entertainment", "gaming", "music",
    "fitness", "news", "science", "comedy", "lifestyle", "other",
]

# Simple per-channel cache (channels rarely change category)
_channel_cache: dict[str, str] = {}

SYSTEM_PROMPT = (
    "你是一个视频内容分类助手。\n"
    "根据视频标题、描述和标签，将视频分类为以下类别之一。\n"
    f"类别列表：{', '.join(CATEGORIES)}\n"
    "只返回一个类别名称，不要有任何其他文字。"
)


async def classify_video_content(
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    *,
    channel_id: str = "",
    client=None,
) -> str:
    """Classify a video's content category.

    Uses SiliconFlow Chat API. Caches per channel_id.

    Returns one of: tech, education, entertainment, gaming, music,
    fitness, news, science, comedy, lifestyle, other
    """
    # Check channel cache
    if channel_id and channel_id in _channel_cache:
        return _channel_cache[channel_id]

    # Build prompt
    tag_str = ", ".join(tags) if tags else ""
    user_prompt = (
        f"标题：{title}\n"
        f"描述：{description[:500]}\n"
        f"标签：{tag_str}\n"
        f"请给这个视频分类。"
    )

    try:
        owns_client = client is None
        if owns_client:
            from app.services.siliconflow.client import get_async_client
            client = get_async_client(timeout=30.0)

        # Use sf_post for retry support
        from app.services.siliconflow.client import sf_post
        resp = await sf_post(client, "chat/completions", json={
            "model": "deepseek-ai/DeepSeek-V4-Flash",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 16,
        })
        data = resp.json()
        category = data["choices"][0]["message"]["content"].strip().lower()

        # Validate category
        if category not in CATEGORIES:
            logger.debug(
                "Unknown category '%s' for '%s', using 'other'",
                category, title[:50],
            )
            category = "other"

        # Cache per channel
        if channel_id:
            _channel_cache[channel_id] = category

        return category

    except Exception as e:
        logger.warning("Content classification failed: %s", e)
        return "other"
    finally:
        if owns_client and client:
            await client.aclose()


def clear_cache() -> None:
    """Clear the channel category cache."""
    _channel_cache.clear()
