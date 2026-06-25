"""Unit tests for SiliconFlow Translate — two-pass ID-marker + polish (v4.0)."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.siliconflow.translate import (
    translate_segments,
    translate_text,
    _segments_to_id_text,
    _parse_id_lines,
    _polish_id_text,
)


# ── _segments_to_id_text ──

def test_segments_to_id_text():
    segments = [
        {"id": 0, "text": "Hello world."},
        {"id": 1, "text": "How are you?"},
    ]
    text = _segments_to_id_text(segments)
    assert text == "[0] Hello world.\n[1] How are you?"


def test_segments_to_id_text_empty():
    assert _segments_to_id_text([]) == ""


# ── _parse_id_lines ──

def test_parse_id_lines_exact():
    content = "[0] 你好世界\n[1] 你好吗"
    result = _parse_id_lines(content, 2)
    assert result == ["你好世界", "你好吗"]


def test_parse_id_lines_wrong_count():
    content = "[0] 你好世界"
    assert _parse_id_lines(content, 2) is None


def test_parse_id_lines_with_code_fence():
    content = "```\n[0] 你好\n[1] 再见\n```"
    result = _parse_id_lines(content, 2)
    assert result == ["你好", "再见"]


def test_parse_id_lines_out_of_order():
    """IDs in wrong order — still maps correctly."""
    content = "[1] 第二句\n[0] 第一句"
    result = _parse_id_lines(content, 2)
    assert result == ["第一句", "第二句"]


def test_parse_id_lines_skips_blank():
    content = "[0] 第一句\n\n[1] 第二句"
    result = _parse_id_lines(content, 2)
    assert result == ["第一句", "第二句"]


def test_parse_id_lines_empty():
    assert _parse_id_lines("", 1) is None


def test_parse_id_lines_extra_noise():
    """Extra text before/after ID lines — still extracts correctly."""
    content = "以下是翻译结果：\n[0] 第一句\n[1] 第二句\n翻译完成。"
    result = _parse_id_lines(content, 2)
    assert result == ["第一句", "第二句"]


# ── translate_segments (two-pass) ──

def _make_id_response(*texts: str) -> str:
    """Build [N] text formatted response."""
    return "\n".join(f"[{i}] {t}" for i, t in enumerate(texts))


def _mock_client(*responses: str) -> AsyncMock:
    """Create an AsyncMock client that returns responses in order."""
    client = AsyncMock()
    call_idx = [0]

    def respond(*args, **kwargs):
        idx = call_idx[0]
        call_idx[0] += 1
        if idx >= len(responses):
            idx = len(responses) - 1
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"choices": [{"message": {"content": responses[idx]}}]}
        return resp

    client.post.side_effect = respond
    return client


@pytest.mark.asyncio
async def test_translate_segments_two_pass():
    """Two-pass translation: pass 1 translates, pass 2 polishes."""
    segments = [
        {"id": 0, "text": "Hello world."},
        {"id": 1, "text": "How are you?"},
    ]
    draft = _make_id_response("你好世界", "你好吗")
    polished = _make_id_response("你好世界！", "你好吗？")

    client = _mock_client(draft, polished)
    result = await translate_segments(client, segments)
    assert result == ["你好世界！", "你好吗？"]
    assert client.post.await_count == 2  # pass 1 + pass 2


@pytest.mark.asyncio
async def test_translate_segments_empty():
    client = AsyncMock()
    result = await translate_segments(client, [])
    assert result == []
    client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_translate_segments_pass1_fail_then_fallback():
    """Pass 1 parse fails → ≤2 segs → fallback to original text (no pass 2)."""
    segments = [
        {"id": 0, "text": "Hello"},
        {"id": 1, "text": "World"},
    ]
    bad_response = "你好\n世界"  # no [N] markers
    client = _mock_client(bad_response)

    result = await translate_segments(client, segments)
    assert len(result) == 2
    assert "Hello" in result[0] or "World" in result[0]


@pytest.mark.asyncio
async def test_translate_segments_malformed_response():
    """Malformed JSON → original text fallback."""
    segments = [{"id": 0, "text": "Hello"}]

    client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json.return_value = {"unexpected": "shape"}
    client.post.return_value = response

    result = await translate_segments(client, segments)
    assert len(result) == 1
    assert "Hello" in result[0]


# ── translate_text ──

@pytest.mark.asyncio
async def test_translate_text_single():
    client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json.return_value = {"choices": [{"message": {"content": "你好"}}]}
    client.post.return_value = response

    result = await translate_text(client, "Hello")
    assert result == "你好"


# ── Binary split for > 60 segments ──

@pytest.mark.asyncio
async def test_translate_segments_binary_split():
    """> 60 segments → auto binary split (each half runs two-pass)."""
    segments = [{"id": i, "text": f"Line {i}"} for i in range(100)]

    call_idx = [0]

    def make_response():
        call_idx[0] += 1
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        # Binary split: 100 → 50+50. Each 50 runs pass1+pass2 = 2 calls.
        # Total: 4 calls. All return same format — parser extracts by [N] ID
        # so it correctly maps regardless of which half.
        texts = [f"行{i}" for i in range(50)]  # always "rows 0..49" — IDs self-correct
        resp.json.return_value = {"choices": [{"message": {"content": _make_id_response(*texts)}}]}
        return resp

    client = AsyncMock()
    client.post.side_effect = lambda *args, **kwargs: make_response()

    result = await translate_segments(client, segments)
    # Binary split: first 50 from left half, next 50 from right half.
    # Both halves return "行0..行49" but ID mapping corrects:
    # - Left [0..49] → 行0..行49
    # - Right [0..49] → 行0..行49, prepended to left → 行0..行49, 行0..行49
    assert len(result) == 100
    assert result[0] == "行0"
    assert result[50] == "行0"
    assert result[99] == "行49"
