"""Phase 8: AI 智能标题与标签生成 (D8-01..D8-08).

基于 SiliconFlow Chat 的 JSON mode，根据视频中文转写内容生成：
- 5 个平实翻译风中文标题候选 (D8-01, D8-02)
- 8 个相关中文标签 (D8-03)
- 中文摘要 (副产品，可用于描述)

调用约定：
- 使用 SiliconFlow Chat JSON mode (response_format={"type": "json_object"})
- 输入：原英文标题 + 中文转写摘要（前 3000 字）
- 单次请求拿到所有结果
- JSON mode 失败时回退到 [TITLES]...[/TITLES] [TAGS]...[/TAGS] 文本格式

设计说明：
- 用 SiliconFlow client.sf_post 而不是 raw httpx，享受 D-04 重试策略
- 函数返回 dict 而非 dataclass，方便上层 JSON 序列化存 DB
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

import httpx

from app.core.storage import get_download_dir
from app.services.siliconflow.client import sf_post, get_async_client

logger = logging.getLogger(__name__)


# 默认模型 — 与 Phase 4 翻译保持一致
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4-Flash"

# 输入文本截断长度（D8 隐含：视频长度决定，3000 字平衡效果与 API 成本）
TRANSCRIPT_MAX_CHARS = 3000


# ── Prompt 模板 (D8-06, D8-07, D8-08) ──
# 平实翻译风：忠实原文信息、平实表达；不用"震惊"等标题党套路
SYSTEM_PROMPT = (
    "你是中文视频标题生成助手，根据视频内容生成 5 个平实、准确、信息丰富的中文标题，每个不超过 30 字。"
    "标题风格：平实翻译风，忠实原文信息，平实表达；不要使用标题党套路；不要带 emoji、不要带 #话题标签。"
    "同时基于视频内容提取 8 个相关中文标签，避免通用词（如 视频、教程）。"
    "并给出一段不超过 200 字的中文内容摘要。"
)


def _build_user_prompt(
    original_title_en: str, transcript_zh: str, *, num_titles: int = 5, num_tags: int = 8
) -> str:
    """构造 user message (D8-07)."""
    truncated = transcript_zh.strip()[:TRANSCRIPT_MAX_CHARS]
    return (
        f"原英文标题（翻译参考）：{original_title_en}\n\n"
        f"视频中文转写摘要（前 {TRANSCRIPT_MAX_CHARS} 字）：\n{truncated}\n\n"
        f"请严格按下面 JSON 格式返回（不要 markdown 代码块、不要任何额外文字）：\n"
        "{"
        f'"titles": ["标题1", "标题2", ..., "标题{num_titles}"], '
        f'"tags": ["标签1", "标签2", ..., "标签{num_tags}"], '
        '"summary_zh": "一段中文摘要（不超过 200 字）"'
        "}"
    )


# ── Public API ──

async def generate_title_candidates(
    video: Any,
    whisper_transcript: Optional[list[dict]] = None,
    original_title_en: Optional[str] = None,
    *,
    configs: Optional[dict[str, str]] = None,
    client: Optional[httpx.AsyncClient] = None,
    model: str = DEFAULT_MODEL,
    num_titles: Optional[int] = None,
    num_tags: Optional[int] = None,
) -> dict[str, Any]:
    """生成 5 个标题候选 + 8 个标签 + 中文摘要.

    Args:
        video: Video ORM 对象（需要 id / title 字段）
        whisper_transcript: 中文转写段列表 [{text, ...}, ...]（未使用，保留接口兼容）
        original_title_en: 原英文标题（默认从 video.title 取）
        configs: 配置项字典（用于覆盖默认值）
        client: 可选 httpx.AsyncClient，便于测试注入
        model: SiliconFlow Chat 模型 ID
        num_titles: 候选标题数（默认从 configs 读，否则 5）
        num_tags: 候选标签数（默认从 configs 读，否则 8）

    Returns:
        {
            "titles": [str, ...]  长度 ≤ num_titles
            "tags":  [str, ...]  长度 ≤ num_tags
            "summary_zh": str
        }
        失败时返回空列表/空字符串，调用方决定是否降级。
    """
    cfg = configs or {}
    title_en = (original_title_en or getattr(video, "title", None) or "").strip()
    if not title_en:
        title_en = f"video-{getattr(video, 'id', 'unknown')}"

    n_titles = int(num_titles if num_titles is not None else cfg.get("title_generator_candidate_count", "5"))
    n_tags = int(num_tags if num_tags is not None else cfg.get("title_generator_tag_count", "8"))

    # 中文转写摘要（Phase 4 的 translated.json 中文段拼接）
    transcript_zh = _resolve_transcript_text(video, whisper_transcript)

    user_prompt = _build_user_prompt(title_en, transcript_zh, num_titles=n_titles, num_tags=n_tags)
    payload = {
        "model": cfg.get("translation_model", model),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.6,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},  # D8 隐含：JSON mode
    }

    owns_client = client is None
    if owns_client:
        client = get_async_client(timeout=60.0)
    try:
        try:
            content = await _request_json_mode(client, payload)
            parsed = _safe_json_parse(content)
            result = validate_candidates(parsed, n_titles, n_tags)
            if result["titles"] or result["tags"]:
                return result
            logger.warning("JSON mode returned empty — falling back to text format")
        except Exception as e:
            logger.warning("JSON mode failed (%s) — falling back to text format", e)

        # 回退：不带 JSON mode 的文本格式（D8 工作规则 6）
        result = await _request_text_fallback(client, payload, title_en, transcript_zh, n_titles, n_tags)
        return result
    finally:
        if owns_client:
            await client.aclose()


async def _request_json_mode(client: httpx.AsyncClient, payload: dict) -> str:
    """执行 JSON mode 请求，返回 content 字符串."""
    resp = await sf_post(client, "chat/completions", json=payload)
    data = resp.json()
    return data["choices"][0]["message"]["content"]


async def _request_text_fallback(
    client: httpx.AsyncClient,
    original_payload: dict,
    title_en: str,
    transcript_zh: str,
    n_titles: int,
    n_tags: int,
) -> dict[str, Any]:
    """JSON mode 失败时的回退：[TITLES]...[/TITLES] [TAGS]...[/TAGS] 文本格式."""
    fallback_prompt = (
        f"原英文标题：{title_en}\n\n"
        f"视频中文摘要（前 {TRANSCRIPT_MAX_CHARS} 字）：\n{transcript_zh[:TRANSCRIPT_MAX_CHARS]}\n\n"
        f"请按以下格式输出（严格按行，不要任何额外解释）：\n"
        f"[TITLES]\n标题1\n标题2\n...\n标题{n_titles}\n[/TITLES]\n"
        f"[TAGS]\n标签1\n标签2\n...\n标签{n_tags}\n[/TAGS]\n"
        f"[SUMMARY]\n中文摘要（不超过 200 字）\n[/SUMMARY]"
    )
    fallback_payload = dict(original_payload)
    fallback_payload.pop("response_format", None)
    fallback_payload["messages"] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": fallback_prompt},
    ]
    fallback_payload["max_tokens"] = 1200

    try:
        resp = await sf_post(client, "chat/completions", json=fallback_payload)
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning("text fallback request failed: %s", e)
        return {"titles": [], "tags": [], "summary_zh": ""}

    return _parse_text_fallback(content, n_titles, n_tags)


_TITLES_BLOCK = re.compile(r"\[TITLES\](.*?)\[/TITLES\]", re.DOTALL)
_TAGS_BLOCK = re.compile(r"\[TAGS\](.*?)\[/TAGS\]", re.DOTALL)
_SUMMARY_BLOCK = re.compile(r"\[SUMMARY\](.*?)\[/SUMMARY\]", re.DOTALL)


def _parse_text_fallback(content: str, n_titles: int, n_tags: int) -> dict[str, Any]:
    """解析 [TITLES]...[/TITLES] [TAGS]...[/TAGS] [SUMMARY]...[/SUMMARY] 文本."""
    def _lines(block_match: Optional[re.Match]) -> list[str]:
        if not block_match:
            return []
        raw = block_match.group(1)
        return [ln.strip().lstrip("-").strip().lstrip("0123456789. ") for ln in raw.splitlines() if ln.strip()]

    titles = _lines(_TITLES_BLOCK.search(content))[:n_titles]
    tags = _lines(_TAGS_BLOCK.search(content))[:n_tags]
    summary_match = _SUMMARY_BLOCK.search(content)
    summary = summary_match.group(1).strip() if summary_match else ""
    return {"titles": titles, "tags": tags, "summary_zh": summary}


def _safe_json_parse(content: str) -> Any:
    """容忍 markdown code fence / 前后噪音的 JSON 解析."""
    s = (content or "").strip()
    if not s:
        return None
    # 去掉 markdown 代码块
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    # 截取最外层 { }
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        s = m.group(0)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def validate_candidates(parsed: Any, num_titles: int = 5, num_tags: int = 8) -> dict[str, Any]:
    """校验 LLM 返回的 JSON 结构，缺失/类型错则返回空列表.

    Args:
        parsed: 已解析的 JSON dict (或 None)
        num_titles: 期望标题数（截断上限）
        num_tags: 期望标签数（截断上限）

    Returns:
        {"titles": [...], "tags": [...], "summary_zh": str}
    """
    if not isinstance(parsed, dict):
        return {"titles": [], "tags": [], "summary_zh": ""}

    raw_titles = parsed.get("titles") or []
    raw_tags = parsed.get("tags") or []
    summary = parsed.get("summary_zh") or parsed.get("summary") or ""

    titles: list[str] = []
    if isinstance(raw_titles, list):
        for t in raw_titles:
            if isinstance(t, str):
                t = t.strip()
                if t:
                    titles.append(t[:80])  # 单条截断保险
            elif t is not None:
                titles.append(str(t).strip()[:80])
            if len(titles) >= num_titles:
                break

    tags: list[str] = []
    if isinstance(raw_tags, list):
        for t in raw_tags:
            if isinstance(t, str):
                t = t.strip()
                if t:
                    tags.append(t[:30])
            elif t is not None:
                tags.append(str(t).strip()[:30])
            if len(tags) >= num_tags:
                break
    elif isinstance(raw_tags, str):
        # 兼容逗号分隔字符串
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()][:num_tags]

    summary = str(summary).strip() if summary else ""

    return {"titles": titles, "tags": tags, "summary_zh": summary}


def _resolve_transcript_text(video: Any, whisper_transcript: Optional[list[dict]]) -> str:
    """从 video 对象或 whisper_transcript 中提取中文文本.

    优先级：
    1. whisper_transcript 参数（如果提供）
    2. 从 downloads/{video_id}/translated.json 读取（Phase 4 输出）
    3. 从 downloads/{video_id}/transcript.json 读取（fallback）
    4. 空字符串
    """
    if whisper_transcript:
        texts = []
        for seg in whisper_transcript:
            if isinstance(seg, dict):
                t = seg.get("text") or ""
            else:
                t = str(seg)
            if t:
                texts.append(t)
        return "\n".join(texts)

    vid = getattr(video, "id", None)
    if not vid:
        return ""

    base = get_download_dir()
    for fname in ("translated.json", "transcript.json"):
        path = os.path.join(base, str(vid), fname)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    texts = []
                    for seg in data:
                        if isinstance(seg, dict):
                            t = seg.get("text") or ""
                        elif isinstance(seg, str):
                            t = seg
                        else:
                            t = ""
                        if t:
                            texts.append(t)
                    if texts:
                        return "\n".join(texts)
                elif isinstance(data, dict):
                    # 可能是 {segments: [...]} 或 {text: ...}
                    if isinstance(data.get("segments"), list):
                        return _resolve_transcript_text(video, data["segments"])
                    if data.get("text"):
                        return str(data["text"])
            except (json.JSONDecodeError, OSError) as e:
                logger.debug("Failed to read transcript %s: %s", path, e)
                continue
    return ""
