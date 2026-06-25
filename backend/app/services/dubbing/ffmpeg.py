"""async ffmpeg subprocess wrapper (P4-20).

约定：
- 所有 ffmpeg 调用走 asyncio.create_subprocess_exec（不用 shell=True，防注入 Threat T-04-07）
- 失败抛 RuntimeError 含 stderr tail
- ffprobe_duration 用同一 API
- Windows 上 asyncio.create_subprocess_exec 要求 ProactorEventLoop，
  自动降级为 subprocess.run + asyncio.to_thread（兼容所有 event loop）
"""
import asyncio
import logging
import os
import subprocess as _subprocess
import sys
from typing import Optional

logger = logging.getLogger(__name__)


async def _run_subprocess(cmd: list[str]) -> tuple[Optional[int], bytes, bytes]:
    """跨平台异步执行子进程，返回 (returncode, stdout, stderr).

    优先使用 asyncio.create_subprocess_exec（Linux/macOS 原生高效），
    Windows 上若 event loop 不支持则降级为 subprocess.run + thread pool。
    不用 shell=True，防注入 Threat T-04-07。
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return (proc.returncode, stdout, stderr)
    except NotImplementedError:
        # Windows: event loop 不支持子进程（如 SelectorEventLoop），
        # 降级为同步 subprocess.run 跑在线程池中，不阻塞 event loop。
        def _run():
            return _subprocess.run(
                cmd,
                capture_output=True,
                timeout=600,
            )
        result = await asyncio.to_thread(_run)
        return (result.returncode, result.stdout, result.stderr)


async def run_ffmpeg_async(cmd: list[str], logger_obj: Optional[logging.Logger] = None) -> int:
    """异步执行命令，返回 exit code；非零抛 RuntimeError.

    Args:
        cmd: 命令列表（参数化，禁止 shell=True）
        logger_obj: 可选 logger
    """
    log = logger_obj or logger
    log.info("ffmpeg exec: %s", " ".join(_quote(c) for c in cmd))

    code, stdout, stderr = await _run_subprocess(cmd)

    if code != 0:
        stderr_tail = (stderr.decode("utf-8", errors="replace") if stderr else "")[-500:]
        raise RuntimeError(f"ffmpeg failed (code={code}): {stderr_tail}")

    return code


def _quote(arg: str) -> str:
    """日志中安全的参数引用."""
    if any(c in arg for c in [" ", "\t", "\n", "'", '"']):
        return repr(arg)
    return arg


async def ffprobe_duration(path: str) -> float:
    """用 ffprobe 读取媒体时长（秒）."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1",
        path,
    ]
    code, stdout, stderr = await _run_subprocess(cmd)
    if code != 0:
        raise RuntimeError(
            f"ffprobe failed: {(stderr or b'').decode('utf-8', errors='replace')}"
        )
    try:
        return float(stdout.decode("utf-8").strip())
    except ValueError as e:
        raise RuntimeError(f"ffprobe: cannot parse duration {stdout!r}") from e


# ── Recipe wrappers ──

async def extract_audio(
    video_path: str,
    out_path: str,
    sample_rate: int = 44100,
    channels: int = 2,
) -> str:
    """Recipe 1: 提取音频为 PCM WAV."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",                        # 无视频
        "-acodec", "pcm_s16le",       # PCM 16-bit
        "-ar", str(sample_rate),      # 采样率
        "-ac", str(channels),         # 声道
        out_path,
    ]
    await run_ffmpeg_async(cmd)
    return out_path


async def extract_audio_mono_16k(
    video_path: str,
    out_path: str,
) -> str:
    """Recipe 2: 提取 16kHz 单声道 WAV (for STT)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        out_path,
    ]
    await run_ffmpeg_async(cmd)
    return out_path


def build_stitch_filter(segments: list[dict]) -> str:
    """构造 -filter_complex 字符串（D-09, D-12 简化）.

    每个 segment 用 adelay 放到正确时间戳，最后 amix 合成整轨。

    Args:
        segments: [{start, end, ...}, ...]，按 start 升序

    Returns:
        filter_complex 字符串，如
        "[1:a]adelay=0|0[a0];[2:a]adelay=2500|2500[a1];[a0][a1]amix=inputs=2:normalize=0:duration=longest[out]"
    """
    if not segments:
        raise ValueError("build_stitch_filter: empty segments")

    parts: list[str] = []
    mix_inputs: list[str] = []

    # 假设调用方按顺序提供 -i each_input.wav，输入索引从 0 开始
    for idx, seg in enumerate(segments):
        # adelay 接受毫秒，按 start 时间定位
        delay_ms = int(round(float(seg.get("start", 0.0)) * 1000))
        # 双声道：左|右
        delay_arg = f"{delay_ms}|{delay_ms}"
        label = f"a{idx}"
        parts.append(f"[{idx}:a]adelay={delay_arg}[{label}]")
        mix_inputs.append(f"[{label}]")

    n = len(segments)
    mix = (
        f"{''.join(mix_inputs)}amix=inputs={n}:normalize=0:duration=longest[out]"
    )
    parts.append(mix)
    return ";".join(parts)


async def stitch_segments(
    aligned_files: list[str],
    segments: list[dict],
    out_path: str,
) -> str:
    """拼接 aligned 文件成整轨（BGM 已弃用，纯静音填充）."""
    if len(aligned_files) != len(segments):
        raise ValueError(
            f"stitch_segments: {len(aligned_files)} files vs {len(segments)} segments"
        )

    filter_complex = build_stitch_filter(segments)

    cmd: list[str] = ["ffmpeg", "-y"]
    for f in aligned_files:
        cmd.extend(["-i", f])
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-ar", "44100",
        "-ac", "2",
        out_path,
    ])
    await run_ffmpeg_async(cmd)
    return out_path


async def compose_video(
    video_path: str,
    audio_path: str,
    out_path: str,
) -> str:
    """Recipe 8: 用新音轨替换原视频音轨."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        out_path,
    ]
    await run_ffmpeg_async(cmd)
    return out_path
