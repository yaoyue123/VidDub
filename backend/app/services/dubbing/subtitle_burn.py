"""Burn bilingual subtitles into video (ASS overlay via ffmpeg).

Produces a final_subtitled.mp4 with:
- Original language subtitles at top of screen (white, smaller)
- Chinese translation subtitles at bottom of screen (yellow, larger)
"""

import logging
import os
from typing import Any

from app.services.dubbing.ffmpeg import run_ffmpeg_async

logger = logging.getLogger(__name__)


def _build_ass_header(font_size: int = 20, position: str = "bottom") -> str:
    """Build ASS header with configurable font size and position.

    Args:
        font_size: Base font size for Chinese subtitles (original is font_size-2).
        position: "bottom" (Chinese at bottom, original at top) or "top".

    Returns:
        ASS header string.
    """
    orig_size = max(font_size - 2, 12)
    cn_size = font_size
    # Alignment: 2=bottom center, 8=top center
    cn_align = 2 if position == "bottom" else 8
    orig_align = 8 if position == "bottom" else 2
    return f"""\
[Script Info]
Title: Bilingual Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Original,Microsoft YaHei,{orig_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,{orig_align},20,20,15,1
Style: Chinese,Microsoft YaHei,{cn_size},&H0000FFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,{cn_align},20,20,15,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _format_ass_timestamp(seconds: float) -> str:
    """Format seconds to ASS timestamp: H:MM:SS.cc (centiseconds)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def write_bilingual_ass(
    segments: list[dict[str, Any]],
    translations: list[str],
    out_path: str,
    font_size: int = 20,
    position: str = "bottom",
) -> str:
    """Generate a bilingual ASS subtitle file.

    Each segment produces two dialogue lines:
    - Original language (Style=Original)
    - Chinese translation (Style=Chinese)

    Args:
        segments: Whisper segments with start/end/text.
        translations: Per-segment Chinese translations (1:1 with segments).
        out_path: Output .ass file path.
        font_size: Base font size for Chinese subtitles (default 20).
        position: Subtitle position ("bottom" or "top").

    Returns:
        out_path
    """
    lines: list[str] = [_build_ass_header(font_size, position)]

    for i, seg in enumerate(segments):
        start_ts = _format_ass_timestamp(float(seg.get("start", 0.0)))
        end_ts = _format_ass_timestamp(float(seg.get("end", 0.0)))

        # Original language (top)
        orig_text = seg.get("text", "").strip()
        if orig_text:
            lines.append(
                f"Dialogue: 0,{start_ts},{end_ts},Original,,0,0,0,,{orig_text}"
            )

        # Chinese translation (bottom)
        zh_text = translations[i] if i < len(translations) else ""
        zh_text = zh_text.strip()
        if zh_text:
            lines.append(
                f"Dialogue: 0,{start_ts},{end_ts},Chinese,,0,0,0,,{zh_text}"
            )

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    content = "\n".join(lines)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("Bilingual ASS written: %s (%d segments)", out_path, len(segments))
    return out_path


async def burn_subtitles_into_video(
    video_path: str,
    ass_path: str,
    out_path: str,
) -> str:
    """Burn ASS subtitles into a video using ffmpeg's ass filter.

    Re-encodes the video stream (required for subtitle burn-in).
    Audio is copied to preserve the dubbed track.

    Args:
        video_path: Input video with dubbed audio.
        ass_path: Bilingual ASS subtitle file.
        out_path: Output video path (e.g. final_subtitled.mp4).

    Returns:
        out_path
    """
    # Normalize path for ffmpeg subtitles filter:
    # - Forward slashes
    # - Escape ':' on Windows (ffmpeg filter graph syntax)
    ass_path_norm = os.path.abspath(ass_path).replace("\\", "/")
    ass_path_norm = ass_path_norm.replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"subtitles='{ass_path_norm}'",
        "-c:a", "copy",
        "-movflags", "+faststart",
        out_path,
    ]
    await run_ffmpeg_async(cmd)
    logger.info("Subtitled video written: %s", out_path)
    return out_path
