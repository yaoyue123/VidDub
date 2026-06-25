"""拼接整轨 (D-12 简化版 — BGM 已弃用).

输入：对齐后的 segments + 时间戳
输出：dubbing.wav，长度 == video_duration
"""
import logging
import os

from app.services.dubbing.ffmpeg import run_ffmpeg_async, stitch_segments

logger = logging.getLogger(__name__)


async def build_dubbing_track(
    aligned_segments: list[dict],
    segments: list[dict],
    video_duration: float,
    out_path: str,
) -> str:
    """拼接对齐后的 segments 成整轨 dubbing.wav.

    Args:
        aligned_segments: 每项含 aligned_path（用于 ffmpeg -i 输入）
        segments: 原始 segments，含 start/end（用于 adelay 时间戳）
        video_duration: 最终视频时长（秒），不足则补静音
        out_path: 输出 wav 路径

    Returns:
        out_path
    """
    if not aligned_segments:
        raise ValueError("build_dubbing_track: no aligned segments")

    if len(aligned_segments) != len(segments):
        raise ValueError(
            f"build_dubbing_track: {len(aligned_segments)} aligned vs {len(segments)} segments"
        )

    # 先用 stitch_segments 拼成中间整轨
    raw_path = out_path + ".raw.wav"
    aligned_files = [s["aligned_path"] for s in aligned_segments]
    await stitch_segments(aligned_files, segments, raw_path)

    # 若总时长 < video_duration，补静音；否则按 video_duration 截断
    raw_duration = await _probe_duration_safe(raw_path)
    if raw_duration >= video_duration - 0.1:
        # 已足够长，截断到 video_duration（避免比视频长）
        cmd = [
            "ffmpeg", "-y",
            "-i", raw_path,
            "-t", f"{video_duration:.3f}",
            "-c", "copy",
            out_path,
        ]
    else:
        # 补静音到 video_duration
        cmd = [
            "ffmpeg", "-y",
            "-i", raw_path,
            "-af", f"apad=whole_dur={video_duration:.3f}",
            "-ar", "44100",
            "-ac", "2",
            out_path,
        ]
    await run_ffmpeg_async(cmd)

    # 清理中间文件
    if os.path.exists(raw_path) and raw_path != out_path:
        try:
            os.remove(raw_path)
        except OSError:
            pass

    logger.info("dubbing track built: %s", out_path)
    return out_path


async def _probe_duration_safe(path: str) -> float:
    """探测时长，失败返回 0."""
    try:
        from app.services.dubbing.ffmpeg import ffprobe_duration
        return await ffprobe_duration(path)
    except Exception as e:
        logger.warning("ffprobe failed for %s: %s", path, e)
        return 0.0
