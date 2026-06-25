"""Unit tests for ffmpeg command construction (P4-20)."""
import os

import pytest

from app.services.dubbing.ffmpeg import (
    build_stitch_filter,
    extract_audio,
    extract_audio_mono_16k,
    compose_video,
    stitch_segments,
)
from app.services.dubbing.paths import video_file, video_work_dir


# ── build_stitch_filter ──

class TestBuildStitchFilter:
    def test_two_segments_basic(self):
        segments = [
            {"start": 0.0, "end": 2.5, "text": "a"},
            {"start": 2.5, "end": 5.0, "text": "b"},
        ]
        result = build_stitch_filter(segments)
        assert "adelay=0|0" in result
        assert "adelay=2500|2500" in result
        assert "amix=inputs=2:normalize=0" in result
        assert "duration=longest" in result

    def test_three_segments(self):
        segments = [
            {"start": 0.0},
            {"start": 1.0},
            {"start": 3.5},
        ]
        result = build_stitch_filter(segments)
        assert "amix=inputs=3:normalize=0" in result
        assert "adelay=0|0" in result
        assert "adelay=1000|1000" in result
        assert "adelay=3500|3500" in result

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            build_stitch_filter([])


# ── extract_audio command ──

class TestExtractAudioCmd:
    @pytest.mark.asyncio
    async def test_extract_audio_default_44100_stereo(self, mock_ffmpeg, tmp_path):
        out = str(tmp_path / "out.wav")
        await extract_audio("input.mp4", out)
        assert len(mock_ffmpeg) == 1
        cmd = mock_ffmpeg[0]
        assert "ffmpeg" in cmd[0]
        assert "-vn" in cmd
        assert "pcm_s16le" in cmd
        assert "44100" in cmd
        assert "2" in cmd

    @pytest.mark.asyncio
    async def test_extract_audio_mono_16k(self, mock_ffmpeg, tmp_path):
        out = str(tmp_path / "out.wav")
        await extract_audio_mono_16k("input.mp4", out)
        cmd = mock_ffmpeg[0]
        assert "16000" in cmd
        assert "1" in cmd


# ── compose_video command ──

class TestComposeVideoCmd:
    @pytest.mark.asyncio
    async def test_compose_default(self, mock_ffmpeg, tmp_path):
        out = str(tmp_path / "final.mp4")
        await compose_video("orig.mp4", "dub.wav", out)
        cmd = mock_ffmpeg[0]
        assert "-map" in cmd
        assert "0:v:0" in cmd
        assert "1:a:0" in cmd
        assert "copy" in cmd
        assert "aac" in cmd
        assert "192k" in cmd
        assert "-shortest" in cmd


# ── stitch_segments ──

class TestStitchSegments:
    @pytest.mark.asyncio
    async def test_stitch_command(self, mock_ffmpeg, tmp_path):
        aligned = [
            str(tmp_path / "a0.wav"),
            str(tmp_path / "a1.wav"),
        ]
        segments = [
            {"start": 0.0, "end": 2.5},
            {"start": 2.5, "end": 5.0},
        ]
        out = str(tmp_path / "out.wav")
        await stitch_segments(aligned, segments, out)
        cmd = mock_ffmpeg[0]
        assert "-filter_complex" in cmd
        idx_fc = cmd.index("-filter_complex")
        filter_val = cmd[idx_fc + 1]
        assert "adelay=0|0" in filter_val
        assert "amix=inputs=2" in filter_val

    @pytest.mark.asyncio
    async def test_stitch_mismatch_raises(self, mock_ffmpeg, tmp_path):
        with pytest.raises(ValueError):
            await stitch_segments(["a.wav"], [{"start": 0}, {"start": 1}], "out.wav")


# ── paths ──

class TestPaths:
    def test_video_work_dir_creates(self, tmp_path):
        d = video_work_dir(1, base_dir=str(tmp_path))
        # 末尾应是路径分隔符 + "1"
        assert d.endswith(os.path.sep + "1") or d.endswith("/1") or d.endswith("\\1")

    def test_video_work_dir_rejects_bad_id(self):
        with pytest.raises(ValueError):
            video_work_dir(-1)
        with pytest.raises(ValueError):
            video_work_dir(0)

    def test_video_file_rejects_traversal(self, tmp_path):
        with pytest.raises(ValueError):
            video_file(1, "../../etc/passwd", base_dir=str(tmp_path))
        with pytest.raises(ValueError):
            video_file(1, "sub/dir", base_dir=str(tmp_path))

    def test_video_file_ok(self, tmp_path):
        p = video_file(1, "original.mp4", base_dir=str(tmp_path))
        assert p.endswith(os.path.join("1", "original.mp4"))
