"""D-15 文件存储约定.

每个视频在 downloads/{video_id}/ 下有统一命名的中间产物：
- original.mp4 / original_audio.wav / transcript.json / translated.json
- dubbing.wav / {title}.mp4 / {title}_subtitled.mp4 / subtitle.srt
"""
import os
import re
import unicodedata
from typing import Any

from app.core.storage import get_download_dir


def sanitize_filename(title: str, max_len: int = 80) -> str:
    """Convert a title into a safe filename stem.

    - Replaces characters invalid on Windows/macOS/Linux: <>:"/\\|?* → _
    - Collapses whitespace and underscores
    - Truncates to max_len (default 80 chars)
    - Strips leading/trailing dots, spaces, underscores

    Returns empty string if no valid chars remain (caller should fall back).
    """
    if not title or not title.strip():
        return ""

    # Normalize Unicode (NFKC for fullwidth -> halfwidth, etc.)
    cleaned = unicodedata.normalize("NFKC", title.strip())

    # Replace invalid filesystem characters
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", cleaned)

    # Collapse consecutive underscores and spaces
    cleaned = re.sub(r"[_\s]+", "_", cleaned)

    # Remove leading/trailing dots, spaces, underscores
    cleaned = cleaned.strip("._ ")

    # Truncate, keeping word boundaries when possible
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("._ ")

    # Remove trailing junk after truncation
    cleaned = cleaned.strip("._ ")

    return cleaned


def video_work_dir(video_id: int, base_dir: str | None = None) -> str:
    """返回 downloads/{video_id}/ 目录（自动创建）."""
    if not isinstance(video_id, int) or video_id <= 0:
        raise ValueError(f"video_id must be a positive int (got {video_id!r})")  # Threat T-04-08
    base_dir = base_dir if base_dir is not None else get_download_dir()
    path = os.path.join(base_dir, str(video_id))
    os.makedirs(path, exist_ok=True)
    return path


def video_file(video_id: int, name: str, base_dir: str | None = None) -> str:
    """返回 downloads/{video_id}/{name} 路径（不创建文件）."""
    # 校验 name 不含路径分隔符（防路径穿越）
    if os.path.sep in name or "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"unsafe filename: {name!r}")  # Threat T-04-08
    return os.path.join(video_work_dir(video_id, base_dir), name)


def group_segments_by_silence(
    segments: list[dict[str, Any]],
    threshold_sec: float = 8.0,
) -> list[dict[str, Any]]:
    """Group consecutive segments into paragraphs split on silence gaps.

    A new paragraph starts when the gap between segment[i].end and
    segment[i+1].start is >= threshold_sec.  This reduces the number of
    TTS calls from one-per-segment to one-per-paragraph, and eliminates
    per-segment atempo artifacts by aligning only paragraph boundaries.

    Args:
        segments: Whisper segments sorted by start time.
                  Each dict must have: start (float), end (float), text (str).
                  May optionally have: id (int).
        threshold_sec: Minimum silence gap to split paragraphs (default 8.0).

    Returns:
        List of paragraph dicts, each with:
            id:         int — 0-based paragraph index
            start:      float — first segment's start time
            end:        float — last segment's end time
            segments:   list[dict] — the segment dicts in this paragraph
            merged_text: str — all segment texts joined with space
    """
    if not segments:
        return []

    paragraphs: list[dict[str, Any]] = []
    current_segs: list[dict[str, Any]] = [segments[0]]

    for i in range(1, len(segments)):
        gap = segments[i]["start"] - segments[i - 1]["end"]
        if gap >= threshold_sec:
            # Flush current paragraph
            paragraphs.append(_make_paragraph(len(paragraphs), current_segs))
            current_segs = [segments[i]]
        else:
            current_segs.append(segments[i])

    # Flush the last paragraph
    paragraphs.append(_make_paragraph(len(paragraphs), current_segs))
    return paragraphs


def _make_paragraph(
    p_id: int, segs: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build a paragraph dict from a list of segments."""
    return {
        "id": p_id,
        "start": float(segs[0]["start"]),
        "end": float(segs[-1]["end"]),
        "segments": segs,
        "merged_text": " ".join(
            s.get("text", "") for s in segs if s.get("text", "").strip()
        ),
    }
