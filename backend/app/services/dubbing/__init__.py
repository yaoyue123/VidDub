"""Dubbing pipeline services (P4-20, P4-40).

模块：
- paths: D-15 文件存储约定
- ffmpeg: async subprocess 封装
- alignment: D-09 atempo + pad/trim 时间对齐
- stitcher: 拼接整轨
- composer: 最终视频合成
- pipeline: 6 步主管线编排 (P4-40)
"""

from app.services.dubbing.paths import video_work_dir, video_file
from app.services.dubbing.ffmpeg import (
    run_ffmpeg_async,
    ffprobe_duration,
    extract_audio,
    extract_audio_mono_16k,
    build_stitch_filter,
    stitch_segments,
    compose_video,
)
from app.services.dubbing.alignment import compute_atempo_chain, align_segment
from app.services.dubbing.stitcher import build_dubbing_track
from app.services.dubbing.composer import compose_final_video

__all__ = [
    "video_work_dir",
    "video_file",
    "run_ffmpeg_async",
    "ffprobe_duration",
    "extract_audio",
    "extract_audio_mono_16k",
    "build_stitch_filter",
    "stitch_segments",
    "compose_video",
    "compute_atempo_chain",
    "align_segment",
    "build_dubbing_track",
    "compose_final_video",
]
