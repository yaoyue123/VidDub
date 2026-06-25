"""SiliconFlow Chat 翻译 — 两轮 ID 标记行翻译 + 润色。

策略：
- Pass 1: 将 segments 构建为 [N] 标记行 → LLM 初步翻译
- Pass 2: 原文 + 初稿 → LLM 从口语化/语境/断句/完整性四维度润色校对
- 用正则提取 [N] 翻译文本，按 ID 映射回 segments
- 若数量不匹配，分半再试（二分回退）
"""
import logging
import re
from typing import Any

import httpx

from app.services.siliconflow.client import sf_post

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4-Flash"

# ── Pass 1: 初步翻译 ──

SYSTEM_PROMPT_TRANSLATE = (
    "你是一位专业的字幕翻译员。\n"
    "规则：\n"
    "1. 每行以 [数字] 开头，后面是待翻译的文本。\n"
    "2. 只翻译文本部分，保留 [数字] 标记完全不变。\n"
    "3. 翻译要简洁自然，适合配音，能在一行时间内念完。\n"
    "4. 使用口语化中文。保留人名、数字、技术术语。\n"
    "5. 每行输出格式： [数字] 翻译后的文本\n"
    "6. 不要输出任何前言、解释、注释、代码块标记。\n"
    "7. 输出行数必须等于输入行数。"
)

# ── Pass 2: 润色校对 ──

SYSTEM_PROMPT_POLISH = (
    "你是一位高级字幕润色专家。我提供了一段原始字幕和它的初步翻译。\n"
    "请对照原文，从以下四个维度对初稿进行审查并输出最终翻译：\n"
    "1. **口语化程度**：读起来是否像真人说话？是否存在生硬的翻译腔？\n"
    "2. **上下文语境**：翻译是否符合当时视频场景的情绪和语境？\n"
    "3. **断句与排版**：结合时间轴，翻译后的句子是否过长？如需换行请合理切分。\n"
    "4. **信息完整性**：是否丢失或歪曲了原文的关键信息？\n"
    "\n"
    "输出规则：\n"
    "1. 每行以 [数字] 开头，输出润色后的中文翻译。\n"
    "2. [数字] 标记必须与原文完全一致，不可增删改。\n"
    "3. 如果初稿已经很好，直接保留不做修改。\n"
    "4. 不要输出任何前言、解释、注释、代码块标记。\n"
    "5. 输出行数必须等于输入行数。"
)

# 匹配 [N] 或 [N/M] 标记开头的行
_ID_LINE = re.compile(r"^\[(\d+)(?:/\d+)?\]\s*(.+)$")


def _segments_to_id_text(segments: list[dict[str, Any]]) -> str:
    """构建带 ID 标记的待翻译文本（每段一行）."""
    lines = []
    for i, seg in enumerate(segments):
        text = seg.get("text", "").strip()
        lines.append(f"[{i}] {text}")
    return "\n".join(lines)


def _parse_id_lines(content: str, expected_count: int) -> list[str] | None:
    """从 LLM 返回内容中提取 [N] 翻译文本，按 ID 排列。

    返回 list[str]，长度应等于 expected_count。
    若解析失败或数量不匹配，返回 None。
    """
    # 去掉可能的代码块标记
    s = content.strip()
    s = re.sub(r"^```[\w]*\s*\n?", "", s, flags=re.MULTILINE)
    s = re.sub(r"\n?```\s*$", "", s)

    # 提取所有 [N] text 行
    id_texts: dict[int, str] = {}
    for line in s.split("\n"):
        m = _ID_LINE.match(line.strip())
        if m:
            idx = int(m.group(1))
            text = m.group(2).strip()
            if text:
                id_texts[idx] = text

    if len(id_texts) != expected_count:
        # Debug: log raw content to diagnose parse failures
        logger.debug(
            "ID parse: got %d/%d translations. Raw content (first 500 chars):\n%s",
            len(id_texts), expected_count,
            content[:500],
        )
        return None

    # 按 ID 排序输出
    return [id_texts[i] for i in range(expected_count)]


async def translate_segments(
    client: httpx.AsyncClient,
    segments: list[dict[str, Any]],
    *,
    model: str = DEFAULT_MODEL,
    context_window: int = 2,  # kept for compatibility
) -> list[str]:
    """翻译 segments → 返回中文翻译列表。

    策略：两轮翻译。
    - Pass 1: [N] 标记行初步翻译
    - Pass 2: 对照原文从口语化/语境/断句/完整性润色校对
    - 若数量不匹配：二分回退重试
    """
    if not segments:
        return []

    id_text = _segments_to_id_text(segments)
    total = len(segments)

    # 短文（≤ 60 段）一次性翻译
    if total <= 60:
        draft = await _translate_id_text(client, id_text, total, model)
        if draft is not None:
            # Pass 2: polish if pass 1 succeeded
            polished = await _polish_id_text(client, id_text, draft, total, model)
            return polished if polished is not None else draft
        # 全文翻译失败，若 ≤ 2 段则原文兜底
        if total <= 2:
            return [_fallback_extract_seg(segments, i) for i in range(total)]
        logger.warning("Pass 1 translation returned invalid count, trying half...")

    # 长文或全文失败：二分递归
    mid = max(total // 2, 1)
    left = await translate_segments(client, segments[:mid], model=model)
    right = await translate_segments(client, segments[mid:], model=model)
    return left + right


async def _translate_id_text(
    client: httpx.AsyncClient,
    id_text: str,
    expected_count: int,
    model: str,
) -> list[str] | None:
    """Pass 1: 翻译带 ID 标记的文本，返回按 ID 排列的翻译列表；失败返回 None."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_TRANSLATE},
            {"role": "user", "content": id_text},
        ],
        "temperature": 0.3,
        "max_tokens": max(4096, expected_count * 200),
    }

    try:
        resp = await sf_post(client, "chat/completions", json=payload)
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning("Pass 1 translate request failed: %s", e)
        return None

    result = _parse_id_lines(content, expected_count)
    if result is None:
        logger.warning(
            "Pass 1 parse failed: expected %d segments, got content %d chars",
            expected_count, len(content),
        )
        return None

    return result


async def _polish_id_text(
    client: httpx.AsyncClient,
    id_text_original: str,
    translations: list[str],
    expected_count: int,
    model: str,
) -> list[str] | None:
    """Pass 2: 润色初稿 — 对照原文从口语化/语境/断句/完整性四个维度审查。

    Args:
        client: HTTP client.
        id_text_original: 原始 [N] text 格式英文。
        translations: Pass 1 翻译结果（中文列表）。
        expected_count: 期望段数。
        model: 模型 ID。

    Returns:
        润色后的翻译列表，或 None（回退用初稿）。
    """
    # 构建润色输入：原文 + 初稿
    polish_input_lines = ["源文本："] + id_text_original.split("\n")
    draft_lines = [f"[{i}] {t}" for i, t in enumerate(translations)]
    polish_input_lines.append("")
    polish_input_lines.append("初稿：")
    polish_input_lines.extend(draft_lines)
    polish_input = "\n".join(polish_input_lines)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_POLISH},
            {"role": "user", "content": polish_input},
        ],
        "temperature": 0.25,
        "max_tokens": max(4096, expected_count * 250),
    }

    try:
        resp = await sf_post(client, "chat/completions", json=payload)
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning("Pass 2 polish request failed: %s", e)
        return None

    result = _parse_id_lines(content, expected_count)
    if result is None:
        logger.warning(
            "Pass 2 parse failed: expected %d segments, got content %d chars — keeping draft",
            expected_count, len(content),
        )
        return None

    logger.info("Pass 2 polish completed: %d segments", len(result))
    return result


def _fallback_extract_seg(segments: list[dict[str, Any]], idx: int) -> str:
    """二分后的小段也失败 → 用原文兜底."""
    if idx < len(segments):
        return segments[idx].get("text", f"[翻译失败:{idx}]")
    return f"[翻译失败:{idx}]"


async def translate_text(
    client: httpx.AsyncClient,
    text: str,
    *,
    model: str = DEFAULT_MODEL,
    source_lang: str = "English",
    target_lang: str = "Chinese",
) -> str:
    """翻译单段文本（用于标题/描述等）."""
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": f"Translate {source_lang} to {target_lang}. Return ONLY the translation, no quotes or explanation.",
            },
            {"role": "user", "content": text},
        ],
        "temperature": 0.2,
        "max_tokens": 2048,
    }
    resp = await sf_post(client, "chat/completions", json=payload)
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()
