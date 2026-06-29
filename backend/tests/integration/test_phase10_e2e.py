"""Phase 10 end-to-end integration smoke test.

目标：在完全无网络环境下验证完整业务链路 + Phase 10 交付物完整性：
    1. pipeline 全链路 (mocked)：POST /api/dub 概念 → chain → composed
    2. SSRF 防护：POST /api/dub 拒绝非 YouTube URL
    3. Phase 10 交付物完整性：所有文档/脚本文件存在 + 含必要章节

不实际调用：
    - 网络 (YouTube / SiliconFlow)
    - ffmpeg subprocess
    - Playwright
    - 真实 Whisper 模型

模拟全部外部依赖；断言 chain 在合理步数内到达 composed (skip 实际 publish)。
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────
# Test 1: SSRF 防护 — POST /api/dub 拒绝非 YouTube URL
# ─────────────────────────────────────────────────────────

def test_phase10_dub_api_rejects_non_youtube_url():
    """POST /api/dub 拒绝非 YouTube URL — SSRF 防护 (CR-03)."""
    from app.api.dub import _validate_youtube_url
    from fastapi import HTTPException

    # 合法 YouTube URL 应通过校验
    _validate_youtube_url("https://www.youtube.com/watch?v=abc123")
    _validate_youtube_url("https://youtu.be/abc123")
    _validate_youtube_url("https://m.youtube.com/watch?v=abc123")

    # 非法 URL：localhost（防 SSRF）
    with pytest.raises(HTTPException) as exc_info:
        _validate_youtube_url("http://127.0.0.1:8080/admin")
    assert exc_info.value.status_code == 422

    # 非法 scheme
    with pytest.raises(HTTPException):
        _validate_youtube_url("ftp://youtube.com/x")

    # 缺 hostname
    with pytest.raises(HTTPException):
        _validate_youtube_url("https://")

    # 非 http(s)
    with pytest.raises(HTTPException):
        _validate_youtube_url("file:///etc/passwd")


# ─────────────────────────────────────────────────────────
# Test 2: scheduler chain 模拟全链路 → 最终达到 composed
# ─────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_phase10_full_pipeline_chain_reaches_composed(
    tmp_path, monkeypatch, sample_segments, sample_translations,
):
    """模拟 6 步 chain：download → transcribe → translate → synthesize → compose.

    断言：
        - 每一步都被调用一次
        - pipeline 完成 final_path 返回
        - 没有 step 调用真实网络 / ffmpeg
    """
    from app.services.dubbing import pipeline as pl

    # ── Mock ffmpeg subprocess ──
    class _FakeProc:
        returncode = 0
        stdout = b""
        stderr = b""

        async def communicate(self):
            return (self.stdout, self.stderr)

        async def wait(self):
            return 0

    ffmpeg_invocations: list[tuple] = []

    async def fake_exec(*args, **kwargs):
        ffmpeg_invocations.append(args)
        cmd = list(args)
        # 输出文件 = 最后一个不以 - 开头且带后缀的参数
        out_candidates = [
            a for a in cmd
            if not a.startswith("-")
            and "." in a
            and a not in ("ffmpeg", "-i")
        ]
        if out_candidates:
            out_path = out_candidates[-1]
            try:
                os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
                with open(out_path, "wb") as f:
                    f.write(b"FAKE_CONTENT")
            except Exception:
                pass
        return _FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    # ── Mock ffprobe ──
    async def fake_probe(path):
        if "original.mp4" in str(path):
            return 12.5
        return 2.0

    monkeypatch.setattr("app.services.dubbing.pipeline.ffprobe_duration", fake_probe)
    monkeypatch.setattr("app.services.dubbing.ffmpeg.ffprobe_duration", fake_probe)
    monkeypatch.setattr("app.services.dubbing.alignment.ffprobe_duration", fake_probe)

    # ── Mock Whisper ──
    whisper_calls: list[tuple] = []

    async def fake_whisper(audio_path, model, lang):
        whisper_calls.append((audio_path, model, lang))
        return sample_segments

    monkeypatch.setattr("app.services.dubbing.pipeline._run_whisper", fake_whisper)

    # ── Mock SiliconFlow httpx client ──
    sf_calls: list[dict] = {}

    http_client = AsyncMock()

    translate_resp = MagicMock()
    translate_resp.status_code = 200
    translate_resp.raise_for_status = MagicMock()
    translate_resp.json.return_value = {
        "choices": [{
            "message": {
                "content": "\n".join(
                    f"[ID:{i}] {t}" for i, t in enumerate(sample_translations)
                )
            }
        }]
    }

    tts_resp = MagicMock()
    tts_resp.status_code = 200
    tts_resp.raise_for_status = MagicMock()
    tts_resp.content = b"FAKE_MP3_DATA"

    def _post_side_effect(url, *args, **kwargs):
        sf_calls.setdefault("post_count", 0)
        sf_calls["post_count"] += 1
        sf_calls.setdefault("urls", []).append(str(url))
        if "chat/completions" in str(url):
            return translate_resp
        return tts_resp

    http_client.post.side_effect = _post_side_effect
    http_client.aclose = AsyncMock()

    # ── 准备 work dir + 视频文件 ──
    work_base = str(tmp_path / "downloads")
    os.makedirs(os.path.join(work_base, "1001"), exist_ok=True)
    video_path = os.path.join(work_base, "1001", "original.mp4")
    with open(video_path, "wb") as f:
        f.write(b"FAKE_VIDEO_BYTES")

    # ── 执行 pipeline ──
    progress_events: list[dict] = []

    async def progress_cb(p):
        progress_events.append(p)

    result = await pl.run_dubbing_pipeline(
        video_id=1001,
        video_path=video_path,
        work_base_dir=work_base,
        whisper_model="tiny",
        http_client=http_client,
        progress_callback=progress_cb,
    )

    # ── 断言：pipeline 完成 ──
    assert "final_path" in result, "pipeline 应返回 final_path"
    assert result["segments_count"] == len(sample_segments)

    # 进度事件最终到 100
    assert progress_events, "应至少有一个进度事件"
    assert progress_events[-1]["percent"] == 100
    assert progress_events[-1]["step"] == "compose"

    # 所有 6 步都被调用
    steps_seen = {p["step"] for p in progress_events}
    expected_steps = {"extract_audio", "transcribe", "translate",
                      "synthesize", "stitch", "compose"}
    missing = expected_steps - steps_seen
    assert not missing, f"缺失步骤: {missing}"

    # Whisper 被调用一次
    assert len(whisper_calls) == 1

    # SiliconFlow 被调用（translate + TTS）
    assert sf_calls.get("post_count", 0) >= 1
    assert any("chat/completions" in u for u in sf_calls.get("urls", []))

    # ffmpeg 被调用多次
    assert len(ffmpeg_invocations) >= 3

    # final_path 对应文件存在
    assert os.path.exists(result["final_path"]), \
        f"final.mp4 应已生成: {result['final_path']}"


# ─────────────────────────────────────────────────────────
# Test 3: VideoStatus 状态机覆盖 — 验证全部状态存在
# ─────────────────────────────────────────────────────────

def test_phase10_video_status_constants_complete():
    """Video.status 应包含全部核心状态常量（per enums.py + ARCHITECTURE.md）.

    enums.py 只为"会写入数据库的"状态提供常量；in-flight 中间态
    如 translating/synthesizing/composing 在 scheduler 内部使用字符串字面量，
    无需常量。这里只校验对外文档化的核心状态。
    """
    from app.models.enums import VideoStatus

    expected = {
        "pending", "downloading", "downloaded",
        "transcribing", "transcribed",
        "translated", "synthesized",
        "composed", "completed", "failed",
    }
    actual = {
        v for k, v in vars(VideoStatus).items()
        if not k.startswith("_") and isinstance(v, str)
    }
    missing = expected - actual
    assert not missing, f"VideoStatus 缺失状态: {missing}"


# ─────────────────────────────────────────────────────────
# Test 4: Phase 10 交付物完整性 — 所有文档/脚本文件存在
# ─────────────────────────────────────────────────────────

def test_phase10_docs_and_scripts_exist():
    """Phase 10 必须交付的所有文件都存在（防止遗漏）."""
    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )

    expected_files = [
        # Setup / start scripts
        "setup.ps1",
        "setup.sh",
        "start.ps1",
        "start.sh",
        # 顶层文档
        "README.md",
        "CHANGELOG.md",
        # docs/
        "docs/ARCHITECTURE.md",
        "docs/API.md",
        "docs/CONFIGURATION.md",
        "docs/TROUBLESHOOTING.md",
        "docs/DEPLOYMENT.md",
        # Phase 10 SUMMARY
        ".planning/phases/10-docker-docs/10-01-SUMMARY.md",
        # Integration test (本文件)
        "backend/tests/integration/test_phase10_e2e.py",
    ]

    missing = []
    for rel in expected_files:
        path = os.path.join(project_root, rel)
        if not os.path.exists(path):
            missing.append(rel)

    assert not missing, f"Phase 10 缺失文件: {missing}"


# ─────────────────────────────────────────────────────────
# Test 5: setup 脚本结构检查（不执行，仅静态检查）
# ─────────────────────────────────────────────────────────

def test_phase10_setup_scripts_have_valid_structure():
    """检查 setup.ps1 / setup.sh / start.ps1 / start.sh 基本结构正确."""
    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )

    # .sh 应有 bash shebang
    for sh_file in ("setup.sh", "start.sh"):
        path = os.path.join(project_root, sh_file)
        with open(path, "r", encoding="utf-8") as f:
            head = f.read(100)
        assert head.startswith("#!/usr/bin/env bash") or head.startswith("#!/bin/bash"), \
            f"{sh_file} 缺少 bash shebang"

    # .ps1 应有 PowerShell 标准结构
    for ps1_file in ("setup.ps1", "start.ps1"):
        path = os.path.join(project_root, ps1_file)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert ".SYNOPSIS" in content or "param(" in content or "[CmdletBinding()]" in content, \
            f"{ps1_file} 缺少 PowerShell 标准结构"


# ─────────────────────────────────────────────────────────
# Test 6: docs 文档基本内容检查（防止空文件）
# ─────────────────────────────────────────────────────────

def test_phase10_docs_have_required_sections():
    """每个 doc 文件应包含其主题核心关键词."""
    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )

    docs_to_check = {
        "README.md": ["VidDub", "setup", "SILICONFLOW_API_KEY"],
        "CHANGELOG.md": ["Phase 10", "Phase 4", "v2.0"],
        "docs/ARCHITECTURE.md": ["mermaid", "scheduler", "状态机"],
        "docs/API.md": ["/api/dub", "WebSocket", "/api/platform"],
        "docs/CONFIGURATION.md": ["SILICONFLOW_API_KEY", "whisper_model", "auto_publish_enabled"],
        "docs/TROUBLESHOOTING.md": ["ffmpeg", "Whisper", "Playwright", "429"],
        "docs/DEPLOYMENT.md": ["nginx", "systemd", "nssm"],
    }

    for rel, keywords in docs_to_check.items():
        path = os.path.join(project_root, rel)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        for kw in keywords:
            assert kw in content, f"{rel} 缺少关键词: {kw!r}"


# ─────────────────────────────────────────────────────────
# Test 7: config_seeder 覆盖所有 Phase 关键配置
# ─────────────────────────────────────────────────────────

def test_phase10_config_seeder_has_all_phase_keys():
    """config_seeder DEFAULT_CONFIGS 应包含各 Phase 引入的关键配置."""
    from app.services.config_seeder import DEFAULT_CONFIGS

    required_keys_per_phase = {
        "phase4": ["tts_voice_simple", "atempo_min", "atempo_max"],
        "phase6": [],  # 平台登录配置不进 DB（走 storage_state）
        "phase7": ["auto_publish_enabled", "publish_retry_max",
                   "bilibili_default_category"],
        "phase8": ["title_generator_enabled", "title_generator_candidate_count",
                   "title_generator_tag_count"],
        "phase9": ["scan_max_concurrent", "scan_default_interval_hours"],
    }

    for phase, keys in required_keys_per_phase.items():
        for k in keys:
            assert k in DEFAULT_CONFIGS, f"{phase}: 配置项 {k!r} 未在 DEFAULT_CONFIGS"
