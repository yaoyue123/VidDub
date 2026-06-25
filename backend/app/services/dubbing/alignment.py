"""atempo + pad/trim 时间对齐算法 (D-09).

策略：
1. 计算 target_ratio = TTS实际时长 / 原segment时长
2. 若 ratio ∈ [atempo_min, atempo_max]（默认 0.7-1.5）→ 纯 atempo 调速
3. 若 ratio > atempo_max → atempo=atempo_max + 截断尾部，action="trim"
4. 若 ratio < atempo_min → atempo=atempo_min + pad 静音到目标，action="pad"
5. atempo 链式支持（ratio>2 或 <0.5 拆分成多段 0.5-2.0）

per RESEARCH §Time Alignment & D-09.
"""
import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Literal

from app.services.dubbing.ffmpeg import ffprobe_duration, run_ffmpeg_async

logger = logging.getLogger(__name__)

# ffmpeg atempo 滤镜有效范围
ATEMPO_FILTER_MIN = 0.5
ATEMPO_FILTER_MAX = 2.0

Action = Literal["atempo", "atempo+pad", "atempo+trim", "skip"]


def compute_atempo_chain(target_ratio: float) -> str:
    """构造 atempo 滤镜链（支持 ratio<0.5 或 >2.0 拆分）.

    WR-05: 这是一个独立 utility — 调用方 `align_segment` 会在传入前把 ratio clamp
    到 [atempo_min, atempo_max]（默认 [0.7, 1.5]，必在 [ATEMPO_FILTER_MIN, MAX]
    内），所以 while 拆分逻辑在当前唯一调用路径下确实不可达。但本函数仍按设计
    保留链式拆分能力，并在 test_alignment.py 中以 ratio=3.0/0.3/4.0/0.2 直接
    测试；若未来扩大 clamp 范围（让 align_segment 走纯 atempo 而非 trim/pad），
    拆分逻辑会自动启用。删除它会损失这部分测试覆盖且无收益。

    Args:
        target_ratio: 目标速率比（如 1.5 表示加快 1.5x）

    Returns:
        滤镜字符串，如 "atempo=1.5000" 或 "atempo=2.0000,atempo=1.5000"

    Examples:
        >>> compute_atempo_chain(1.2)
        'atempo=1.2000'
        >>> compute_atempo_chain(0.5)
        'atempo=0.5000'
        >>> compute_atempo_chain(3.0)
        'atempo=2.0000,atempo=1.5000'
        >>> compute_atempo_chain(0.3)
        'atempo=0.5000,atempo=0.6000'
    """
    if target_ratio <= 0:
        raise ValueError(f"target_ratio must be > 0, got {target_ratio}")

    ratio = target_ratio
    chain: list[str] = []

    # 若 ratio 超出 [0.5, 2.0]，链式拆分
    while ratio > ATEMPO_FILTER_MAX:
        chain.append(f"atempo={ATEMPO_FILTER_MAX:.4f}")
        ratio /= ATEMPO_FILTER_MAX

    while ratio < ATEMPO_FILTER_MIN:
        chain.append(f"atempo={ATEMPO_FILTER_MIN:.4f}")
        ratio /= ATEMPO_FILTER_MIN

    # 剩余比例（必在 [0.5, 2.0]）
    chain.append(f"atempo={ratio:.4f}")

    return ",".join(chain)


@dataclass
class AlignResult:
    aligned_path: str
    target_duration: float
    actual_duration: float
    ratio: float
    action: Action


async def align_segment(
    tts_audio_path: str,
    seg_start: float,
    seg_end: float,
    out_path: str,
    atempo_min: float = 0.7,
    atempo_max: float = 1.5,
) -> AlignResult:
    """对齐单段 TTS 音频到 [seg_start, seg_end] 区间.

    Returns:
        AlignResult(aligned_path, target_duration, actual_duration, ratio, action)
    """
    if seg_end <= seg_start:
        raise ValueError(f"invalid segment [{seg_start}, {seg_end}]")

    target_duration = seg_end - seg_start
    actual_duration = await ffprobe_duration(tts_audio_path)

    if actual_duration <= 0:
        raise RuntimeError(f"TTS audio has zero duration: {tts_audio_path}")

    ratio = actual_duration / target_duration
    action: Action = "atempo"

    # 边界 clamp（D-09）
    applied_ratio = ratio
    if ratio > atempo_max:
        applied_ratio = atempo_max
        action = "atempo+trim"
        logger.warning(
            "segment [%.2f-%.2f]: ratio=%.2f > atempo_max=%.2f, will trim",
            seg_start, seg_end, ratio, atempo_max,
        )
    elif ratio < atempo_min:
        applied_ratio = atempo_min
        action = "atempo+pad"
        logger.warning(
            "segment [%.2f-%.2f]: ratio=%.2f < atempo_min=%.2f, will pad silence",
            seg_start, seg_end, ratio, atempo_min,
        )

    # Step 1: 应用 atempo 链
    atempo_filter = compute_atempo_chain(applied_ratio)
    tempo_path = out_path + ".tempo.wav"
    cmd = [
        "ffmpeg", "-y",
        "-i", tts_audio_path,
        "-af", atempo_filter,
        "-ar", "44100",
        "-ac", "2",
        tempo_path,
    ]
    await run_ffmpeg_async(cmd)

    # Step 2: trim 或 pad
    if action == "atempo+trim":
        # 截断到 target_duration
        cmd = [
            "ffmpeg", "-y",
            "-i", tempo_path,
            "-t", f"{target_duration:.3f}",
            "-c", "copy",
            out_path,
        ]
        await run_ffmpeg_async(cmd)
    elif action == "atempo+pad":
        # 用 apad 补静音到 target_duration
        cmd = [
            "ffmpeg", "-y",
            "-i", tempo_path,
            "-af", f"apad=whole_dur={target_duration:.3f}",
            "-ar", "44100",
            "-ac", "2",
            out_path,
        ]
        await run_ffmpeg_async(cmd)
    else:
        # 纯 atempo，可能略有偏差但接受。
        # CR-04: run_ffmpeg_async 成功时 tempo_path 必须存在；若不存在说明上游
        # ffmpeg 调用静默失败（磁盘满 / antivirus / race 等），必须当作真实错误传播，
        # 不能再写空文件兜底 — 否则 stitcher 会把 0 字节 wav 拼进 dubbing.wav，
        # 静默破坏最终视频音频。
        os.replace(tempo_path, out_path)

    # 清理中间文件
    if os.path.exists(tempo_path) and tempo_path != out_path:
        try:
            os.remove(tempo_path)
        except OSError:
            pass

    return AlignResult(
        aligned_path=out_path,
        target_duration=target_duration,
        actual_duration=actual_duration,
        ratio=ratio,
        action=action,
    )
