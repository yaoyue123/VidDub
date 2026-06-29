"""Shared pytest fixtures for viddub backend tests."""
import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# 加载 .env（如存在）让 Settings/api_key 读取正常
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# 单元测试兜底：若无 API key 则用 placeholder（仅 mock 测试不会真调）
os.environ.setdefault("SILICONFLOW_API_KEY", "sk-test-key-for-unit-tests")


# ── Sample data ──

@pytest.fixture
def sample_segments() -> list[dict]:
    """标准 5 段测试 segments（模拟 Whisper 输出）."""
    return [
        {"id": 0, "start": 0.0, "end": 2.5, "text": "Hello everyone, welcome to this video."},
        {"id": 1, "start": 2.5, "end": 5.0, "text": "Today we will talk about AI."},
        {"id": 2, "start": 5.0, "end": 7.5, "text": "AI is changing the world."},
        {"id": 3, "start": 7.5, "end": 10.0, "text": "Let's start with the basics."},
        {"id": 4, "start": 10.0, "end": 12.5, "text": "Thank you for watching."},
    ]


@pytest.fixture
def sample_translations() -> list[str]:
    """对应 sample_segments 的中文翻译（模拟 SiliconFlow 输出）."""
    return [
        "大家好，欢迎观看本视频。",
        "今天我们将谈论人工智能。",
        "人工智能正在改变世界。",
        "让我们从基础开始。",
        "感谢您的观看。",
    ]


@pytest.fixture
def sample_en_audio() -> str:
    """Fixture WAV 路径（13.77 秒英文 TTS 测试音频）."""
    return str(FIXTURES_DIR / "sample_en.wav")


# ── Mocks ──

@pytest.fixture
def mock_sf_client():
    """Mock httpx.AsyncClient — 返回预设响应，断言调用参数."""
    client = AsyncMock()
    # 默认 200 响应
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json.return_value = {"segments": []}
    response.content = b"\x00\x01\x02\x03FAKE_AUDIO"
    client.post.return_value = response
    client.get.return_value = response
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    return client


@pytest.fixture
def mock_ffmpeg(monkeypatch):
    """Patch asyncio.create_subprocess_exec — 记录调用但不实际执行 ffmpeg."""
    calls = []

    class FakeProc:
        returncode = 0
        stdout = b""
        stderr = b""

        async def communicate(self):
            return (self.stdout, self.stderr)

        async def wait(self):
            return 0

    async def fake_exec(*args, **kwargs):
        calls.append(list(args))
        return FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    return calls


@pytest.fixture
def tmp_workdir(tmp_path):
    """临时 downloads/{vid}/ 工作目录."""
    work = tmp_path / "downloads" / "1"
    work.mkdir(parents=True)
    return str(work)
