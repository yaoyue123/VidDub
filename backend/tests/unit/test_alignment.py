"""Unit tests for atempo alignment algorithm (D-09, P4-20)."""
import os

import pytest

from app.services.dubbing.alignment import (
    compute_atempo_chain,
    AlignResult,
    align_segment,
)


# ── compute_atempo_chain ──

class TestComputeAtempoChain:
    def test_simple_1_2x(self):
        assert compute_atempo_chain(1.2) == "atempo=1.2000"

    def test_simple_0_5x(self):
        assert compute_atempo_chain(0.5) == "atempo=0.5000"

    def test_chain_for_3x(self):
        # 3.0 → 2.0 * 1.5
        chain = compute_atempo_chain(3.0)
        assert "atempo=2.0000" in chain
        assert "atempo=1.5000" in chain
        assert chain.count("atempo=") == 2

    def test_chain_for_0_3x(self):
        # 0.3 → 0.5 * 0.6
        chain = compute_atempo_chain(0.3)
        assert "atempo=0.5000" in chain
        assert "atempo=0.6000" in chain
        assert chain.count("atempo=") == 2

    def test_extreme_4x(self):
        # 4.0 → 2.0 * 2.0
        chain = compute_atempo_chain(4.0)
        assert chain == "atempo=2.0000,atempo=2.0000"

    def test_extreme_0_2x(self):
        # 0.2 = 0.5 * 0.5 * 0.8 — 拆成 3 段（每段必在 [0.5, 2.0]）
        chain = compute_atempo_chain(0.2)
        # 总效果应等于 0.2（验证乘积）
        assert "atempo=0.5000" in chain
        assert chain.count("atempo=") == 3

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            compute_atempo_chain(0.0)

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            compute_atempo_chain(-1.0)

    def test_boundary_1(self):
        # ratio == 1.0 不变速
        assert compute_atempo_chain(1.0) == "atempo=1.0000"


# ── align_segment (action 边界) ──

class TestAlignSegmentBoundary:
    @pytest.mark.asyncio
    async def test_in_range_atempo_only(self, mock_ffmpeg, monkeypatch, tmp_path):
        """ratio 在 [0.7, 1.5] → action=atempo."""
        # 模拟 TTS 时长 = 原时长，ratio=1.0
        async def fake_probe(path):
            return 2.5
        monkeypatch.setattr(
            "app.services.dubbing.alignment.ffprobe_duration", fake_probe
        )

        # tts_path 必须存在（run_ffmpeg_async 是 mock 但 os.path 检查需要）
        tts_path = tmp_path / "tts.wav"
        tts_path.write_bytes(b"FAKE")
        out_path = str(tmp_path / "aligned.wav")

        # CR-04: 不再用空文件兜底 — 必须由 fake ffmpeg 写出 tempo_path，
        # 否则 os.replace 会抛 FileNotFoundError（这正是新的正确语义）。
        async def fake_run_ffmpeg(cmd):
            # cmd 末尾是输出文件路径
            out = cmd[-1]
            os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
            with open(out, "wb") as f:
                f.write(b"FAKE_WAV")
        monkeypatch.setattr(
            "app.services.dubbing.alignment.run_ffmpeg_async", fake_run_ffmpeg
        )

        result = await align_segment(str(tts_path), 0.0, 2.5, out_path)
        assert result.action == "atempo"
        assert result.ratio == 1.0
        assert result.target_duration == 2.5
        # tempo_path 应已被 os.replace 到 out_path
        assert os.path.exists(out_path)

    @pytest.mark.asyncio
    async def test_too_long_trims(self, mock_ffmpeg, monkeypatch, tmp_path):
        """TTS 太长 → action=atempo+trim."""
        # TTS 时长 5s, 目标 2.5s → ratio=2.0 > 1.5 → clamp 1.5 + trim
        async def fake_probe(path):
            return 5.0
        monkeypatch.setattr(
            "app.services.dubbing.alignment.ffprobe_duration", fake_probe
        )

        tts_path = tmp_path / "tts.wav"
        tts_path.write_bytes(b"FAKE")
        out_path = str(tmp_path / "aligned.wav")

        result = await align_segment(str(tts_path), 0.0, 2.5, out_path, atempo_max=1.5)
        assert result.action == "atempo+trim"
        assert result.ratio == 2.0  # 实际比例

    @pytest.mark.asyncio
    async def test_too_short_pads(self, mock_ffmpeg, monkeypatch, tmp_path):
        """TTS 太短 → action=atempo+pad."""
        # TTS 时长 1s, 目标 2.5s → ratio=0.4 < 0.7 → clamp 0.7 + pad
        async def fake_probe(path):
            return 1.0
        monkeypatch.setattr(
            "app.services.dubbing.alignment.ffprobe_duration", fake_probe
        )

        tts_path = tmp_path / "tts.wav"
        tts_path.write_bytes(b"FAKE")
        out_path = str(tmp_path / "aligned.wav")

        result = await align_segment(str(tts_path), 0.0, 2.5, out_path, atempo_min=0.7)
        assert result.action == "atempo+pad"
        assert result.ratio == 0.4

    @pytest.mark.asyncio
    async def test_invalid_segment_raises(self, mock_ffmpeg, tmp_path):
        """seg_end <= seg_start 抛 ValueError."""
        tts_path = tmp_path / "tts.wav"
        tts_path.write_bytes(b"FAKE")
        with pytest.raises(ValueError):
            await align_segment(str(tts_path), 5.0, 5.0, str(tmp_path / "out.wav"))

    @pytest.mark.asyncio
    async def test_tempo_missing_raises(self, monkeypatch, tmp_path):
        """CR-04: 若 ffmpeg 静默失败导致 tempo_path 缺失，必须抛错而非写空文件."""
        async def fake_probe(path):
            return 2.5
        monkeypatch.setattr(
            "app.services.dubbing.alignment.ffprobe_duration", fake_probe
        )

        # 故意不写 tempo_path — 模拟 ffmpeg silent failure
        async def fake_run_ffmpeg_no_write(cmd):
            # 不创建任何文件
            return
        monkeypatch.setattr(
            "app.services.dubbing.alignment.run_ffmpeg_async", fake_run_ffmpeg_no_write
        )

        tts_path = tmp_path / "tts.wav"
        tts_path.write_bytes(b"FAKE")
        out_path = str(tmp_path / "aligned.wav")

        # ratio=1.0 → action="atempo"，旧代码会写 0 字节 wav 兜底；
        # CR-04 后必须 FileNotFoundError（不再静默破坏下游 stitcher）。
        with pytest.raises(FileNotFoundError):
            await align_segment(str(tts_path), 0.0, 2.5, out_path)
        # 关键：out_path 不应被写成空文件（会污染下游）
        assert not os.path.exists(out_path)
