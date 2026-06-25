"""SiliconFlow TTS — CosyVoice2-0.5B 合成 (D-03).

参数：
- voice: 默认 'alex'（女声），自动拼 'model:voice' 前缀
- response_format: mp3/wav/opus/pcm
- speed: 0.25-4.0
- gain: -10 to 10 dB
"""
import logging
import os
from typing import Any, Optional

import httpx

from app.services.siliconflow.client import sf_post_bytes

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "FunAudioLLM/CosyVoice2-0.5B"
DEFAULT_VOICE = "anna"

# 可用音色（SiliconFlow 官方文档）
# 男声：alex, benjamin, charles, david
# 女声：anna, bella, claire, diana
AVAILABLE_VOICES = [
    "alex", "benjamin", "charles", "david",       # 男声
    "anna", "bella", "claire", "diana",            # 女声
]

# 参数范围（per SiliconFlow API 文档）
SPEED_MIN, SPEED_MAX = 0.25, 4.0
GAIN_MIN, GAIN_MAX = -10.0, 10.0
TEXT_MAX_CHARS = 128_000


def _qualify_voice(voice: str, model: str) -> str:
    """voice 不含 ':' 时自动拼前缀 'model:voice'."""
    if ":" in voice:
        return voice
    return f"{model}:{voice}"


def _validate_params(text: str, speed: float, gain: float) -> None:
    if not text or len(text) > TEXT_MAX_CHARS:
        raise ValueError(f"text length must be 1-{TEXT_MAX_CHARS}, got {len(text)}")
    if not (SPEED_MIN <= speed <= SPEED_MAX):
        raise ValueError(f"speed must be {SPEED_MIN}-{SPEED_MAX}, got {speed}")
    if not (GAIN_MIN <= gain <= GAIN_MAX):
        raise ValueError(f"gain must be {GAIN_MIN}-{GAIN_MAX}, got {gain}")


async def synthesize_speech(
    client: httpx.AsyncClient,
    text: str,
    out_path: str,
    *,
    model: str = DEFAULT_MODEL,
    voice: str = DEFAULT_VOICE,
    response_format: str = "mp3",
    speed: float = 1.0,
    gain: float = 0.0,
    stream: bool = False,
) -> str:
    """合成语音，写入 out_path，返回 out_path.

    Args:
        client: httpx.AsyncClient
        text: 待合成文本（中英文均可，CosyVoice2 自动识别）
        out_path: 输出文件路径（后缀应与 response_format 一致）
        model: SiliconFlow TTS 模型 ID
        voice: 音色名（如 'alex'），不含 ':' 时自动拼 model 前缀
        response_format: mp3/wav/opus/pcm
        speed: 语速 0.25-4.0
        gain: 增益 dB -10 to 10
        stream: 是否流式（True 时返回 server-sent events；本实现按非流式处理）
    """
    _validate_params(text, speed, gain)

    payload: dict[str, Any] = {
        "model": model,
        "input": text,
        "voice": _qualify_voice(voice, model),
        "response_format": response_format,
        "stream": bool(stream),
        "speed": float(speed),
        "gain": float(gain),
    }

    audio_bytes = await sf_post_bytes(client, "audio/speech", json=payload)

    if not audio_bytes:
        raise RuntimeError(f"SiliconFlow TTS returned empty audio for text: {text[:50]!r}")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(audio_bytes)

    logger.info("TTS synthesized %d bytes -> %s", len(audio_bytes), out_path)
    return out_path
