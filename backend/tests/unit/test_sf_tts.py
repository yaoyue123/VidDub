"""Unit tests for SiliconFlow TTS (P4-10)."""
import os

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.siliconflow.tts import (
    synthesize_speech,
    AVAILABLE_VOICES,
    DEFAULT_MODEL,
    _qualify_voice,
    _validate_params,
)


def test_available_voices_contains_alex():
    """默认音色 alex 必须在列表."""
    assert "alex" in AVAILABLE_VOICES


def test_qualify_voice_adds_model_prefix():
    """voice 不含 ':' 时自动拼前缀."""
    assert _qualify_voice("alex", "FunAudioLLM/CosyVoice2-0.5B") == "FunAudioLLM/CosyVoice2-0.5B:alex"


def test_qualify_voice_preserves_prefix():
    """voice 含 ':' 时保持原样."""
    qualified = "FunAudioLLM/CosyVoice2-0.5B:alex"
    assert _qualify_voice(qualified, "FunAudioLLM/CosyVoice2-0.5B") == qualified


def test_validate_params_ok():
    _validate_params("hello", speed=1.0, gain=0.0)
    _validate_params("x" * 128000, speed=4.0, gain=10.0)


def test_validate_params_text_too_long():
    with pytest.raises(ValueError, match="text length"):
        _validate_params("", speed=1.0, gain=0.0)
    with pytest.raises(ValueError, match="text length"):
        _validate_params("x" * 128001, speed=1.0, gain=0.0)


def test_validate_params_speed_out_of_range():
    with pytest.raises(ValueError, match="speed"):
        _validate_params("hello", speed=0.1, gain=0.0)
    with pytest.raises(ValueError, match="speed"):
        _validate_params("hello", speed=5.0, gain=0.0)


def test_validate_params_gain_out_of_range():
    with pytest.raises(ValueError, match="gain"):
        _validate_params("hello", speed=1.0, gain=-20.0)
    with pytest.raises(ValueError, match="gain"):
        _validate_params("hello", speed=1.0, gain=20.0)


@pytest.mark.asyncio
async def test_synthesize_speech_writes_file(tmp_path):
    """合成语音写入文件."""
    fake_audio = b"FAKE_MP3_BYTES"

    client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.content = fake_audio
    client.post.return_value = response

    out_path = str(tmp_path / "tts_001.mp3")
    result = await synthesize_speech(client, "你好世界", out_path, voice="alex")

    assert result == out_path
    assert os.path.exists(out_path)
    with open(out_path, "rb") as f:
        assert f.read() == fake_audio

    # 验证请求 body 含必需字段
    args, kwargs = client.post.call_args
    body = kwargs["json"]
    assert body["model"] == DEFAULT_MODEL
    assert body["input"] == "你好世界"
    assert body["voice"] == "FunAudioLLM/CosyVoice2-0.5B:alex"  # 自动拼前缀
    assert body["response_format"] == "mp3"
    assert body["speed"] == 1.0
    assert body["gain"] == 0.0
    assert body["stream"] is False


@pytest.mark.asyncio
async def test_synthesize_speech_empty_audio_raises(tmp_path):
    """TTS 返回空音频抛 RuntimeError."""
    client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.content = b""
    client.post.return_value = response

    out_path = str(tmp_path / "tts_002.mp3")
    with pytest.raises(RuntimeError, match="empty audio"):
        await synthesize_speech(client, "test", out_path)


@pytest.mark.asyncio
async def test_synthesize_speech_custom_voice_prefix(tmp_path):
    """自定义 voice 已含 ':' 时保持原样."""
    client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.content = b"FAKE"
    client.post.return_value = response

    out_path = str(tmp_path / "tts_003.mp3")
    await synthesize_speech(
        client, "test", out_path,
        voice="FunAudioLLM/CosyVoice2-0.5B:bella",
    )
    args, kwargs = client.post.call_args
    assert kwargs["json"]["voice"] == "FunAudioLLM/CosyVoice2-0.5B:bella"
