"""Integration test for end-to-end dubbing pipeline (P4-61).

不依赖网络 — 全部用 mock httpx + mock ffmpeg 覆盖。
"""
import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def fake_transcript_file(tmp_path):
    """5 段假 transcript.json fixture."""
    segments = [
        {"id": 0, "start": 0.0, "end": 2.5, "text": "Hello world."},
        {"id": 1, "start": 2.5, "end": 5.0, "text": "How are you?"},
        {"id": 2, "start": 5.0, "end": 7.5, "text": "AI is great."},
        {"id": 3, "start": 7.5, "end": 10.0, "text": "Let's learn."},
        {"id": 4, "start": 10.0, "end": 12.5, "text": "Goodbye."},
    ]
    path = tmp_path / "transcript.json"
    path.write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")
    return segments, str(path)


# ── Test 1: pipeline 全流程 mock ──

@pytest.mark.asyncio
async def test_pipeline_full_run_mocked(tmp_path, monkeypatch, sample_segments, sample_translations):
    """调 run_dubbing_pipeline，断言所有 step 调用、progress_callback 累计到 100."""
    from app.services.dubbing import pipeline as pl

    # Mock httpx client（translate + tts 都用）
    http_client = AsyncMock()
    # translate 返回
    translate_resp = MagicMock()
    translate_resp.status_code = 200
    translate_resp.raise_for_status = MagicMock()
    translate_resp.json.return_value = {
        "choices": [{"message": {"content": "\n".join(
            f"[ID:{i}] {t}" for i, t in enumerate(sample_translations)
        )}}]
    }
    # tts 返回（每次 post 都返回不同的 mock，但 content 一致即可）
    tts_resp = MagicMock()
    tts_resp.status_code = 200
    tts_resp.raise_for_status = MagicMock()
    tts_resp.content = b"FAKE_MP3"
    # sf_post 内部把 retry policy 包了，简单 mock 直接调底层 post
    http_client.post.side_effect = [translate_resp] + [tts_resp] * 10
    http_client.aclose = AsyncMock()

    # Mock ffmpeg subprocess
    ffmpeg_calls = []

    class FakeProc:
        returncode = 0
        stdout = b""
        stderr = b""

        async def communicate(self):
            return (self.stdout, self.stderr)

        async def wait(self):
            return 0

    async def fake_exec(*args, **kwargs):
        ffmpeg_calls.append(args[0] if args else None)
        # 模拟 ffmpeg 写出文件
        # 找 -i 后面的输入和最后一个 out 参数
        return FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    # 让 ffprobe_duration 返回固定值（patch 所有引用处）
    async def fake_probe(path):
        if "original.mp4" in path:
            return 12.5
        return 2.0
    monkeypatch.setattr("app.services.dubbing.pipeline.ffprobe_duration", fake_probe)
    monkeypatch.setattr("app.services.dubbing.ffmpeg.ffprobe_duration", fake_probe)
    monkeypatch.setattr("app.services.dubbing.alignment.ffprobe_duration", fake_probe)

    # Mock Whisper
    async def fake_whisper(audio, model, lang):
        return sample_segments
    monkeypatch.setattr("app.services.dubbing.pipeline._run_whisper", fake_whisper)

    # 让 extract_audio 不真的失败 — fake_exec 返回 0 即可，但需要文件存在让 exists() 判断
    # 改让 pipeline 跳过 extract（先建空文件）
    work_base = str(tmp_path / "downloads")
    os.makedirs(os.path.join(work_base, "999"), exist_ok=True)
    # 预创建视频文件
    video_path = os.path.join(work_base, "999", "original.mp4")
    open(video_path, "wb").close()

    # 让文件在 ffmpeg 调用后被"创建"：每次 exec 后写 fake 文件
    original_exec = fake_exec

    async def fake_exec_with_files(*args, **kwargs):
        await original_exec(*args, **kwargs)
        # 最后一个非 -flag 参数是输出路径
        cmd = list(args)
        # 找出输出文件（最后一个不以 - 开头的参数）
        out_candidates = [a for a in cmd if not a.startswith("-") and "." in a and a != "ffmpeg" and "ffmpeg" not in a]
        if out_candidates:
            out_path = out_candidates[-1]
            try:
                os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
                with open(out_path, "wb") as f:
                    f.write(b"FAKE")
            except Exception:
                pass
        return FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec_with_files)

    progresses: list[dict] = []

    async def cb(p):
        progresses.append(p)

    # 调用 pipeline
    result = await pl.run_dubbing_pipeline(
        video_id=999,
        video_path=video_path,
        work_base_dir=work_base,
        whisper_model="tiny",
        http_client=http_client,
        progress_callback=cb,
    )

    # 断言
    assert "final_path" in result
    assert result["segments_count"] == 5
    # progress 累计应到 100
    assert progresses[-1]["percent"] == 100
    assert progresses[-1]["step"] == "compose"
    # 必须经过所有 step
    steps_seen = {p["step"] for p in progresses}
    assert "extract_audio" in steps_seen
    assert "transcribe" in steps_seen
    assert "translate" in steps_seen
    assert "synthesize" in steps_seen
    assert "stitch" in steps_seen
    assert "compose" in steps_seen


# ── Test 2: STT 失败传播 ──

@pytest.mark.asyncio
async def test_pipeline_stt_failure_propagates(tmp_path, monkeypatch):
    """Whisper 失败时 pipeline 应抛异常."""
    from app.services.dubbing import pipeline as pl

    async def fake_whisper_fail(audio, model, lang):
        raise RuntimeError("Whisper failed: model not loaded")
    monkeypatch.setattr("app.services.dubbing.pipeline._run_whisper", fake_whisper_fail)

    async def fake_probe(path):
        return 12.5
    monkeypatch.setattr("app.services.dubbing.pipeline.ffprobe_duration", fake_probe)

    class FakeProc:
        returncode = 0
        stdout = b""
        stderr = b""

        async def communicate(self):
            return (self.stdout, self.stderr)

    async def fake_exec(*args, **kwargs):
        cmd = list(args)
        outs = [a for a in cmd if not a.startswith("-") and "." in a and a != "ffmpeg"]
        if outs:
            try:
                os.makedirs(os.path.dirname(outs[-1]) or ".", exist_ok=True)
                open(outs[-1], "wb").close()
            except Exception:
                pass
        return FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    work_base = str(tmp_path / "downloads")
    os.makedirs(os.path.join(work_base, "888"), exist_ok=True)
    video_path = os.path.join(work_base, "888", "original.mp4")
    open(video_path, "wb").close()

    http_client = AsyncMock()
    http_client.aclose = AsyncMock()

    with pytest.raises(RuntimeError, match="Whisper failed"):
        await pl.run_dubbing_pipeline(
            video_id=888, video_path=video_path,
            work_base_dir=work_base,
            http_client=http_client,
        )


# ── Test 3: resume_from 跳过已完成步骤 ──

@pytest.mark.asyncio
async def test_pipeline_resume_from_translate(tmp_path, monkeypatch, sample_segments, sample_translations):
    """resume_from='translated' 时跳过 transcribe."""
    from app.services.dubbing import pipeline as pl

    work_base = str(tmp_path / "downloads")
    os.makedirs(os.path.join(work_base, "777"), exist_ok=True)
    video_path = os.path.join(work_base, "777", "original.mp4")
    open(video_path, "wb").close()

    # 预置 transcript.json + translated.json
    import json as _json
    with open(os.path.join(work_base, "777", "transcript.json"), "w", encoding="utf-8") as f:
        _json.dump(sample_segments, f)
    with open(os.path.join(work_base, "777", "translated.json"), "w", encoding="utf-8") as f:
        _json.dump(sample_translations, f)

    whisper_called = []

    async def fake_whisper(audio, model, lang):
        whisper_called.append(True)
        return sample_segments
    monkeypatch.setattr("app.services.dubbing.pipeline._run_whisper", fake_whisper)

    # Mock ffmpeg
    class FakeProc:
        returncode = 0
        stdout = b""
        stderr = b""

        async def communicate(self):
            return (self.stdout, self.stderr)

    async def fake_exec(*args, **kwargs):
        cmd = list(args)
        outs = [a for a in cmd if not a.startswith("-") and "." in a and a != "ffmpeg"]
        if outs:
            try:
                os.makedirs(os.path.dirname(outs[-1]) or ".", exist_ok=True)
                open(outs[-1], "wb").close()
            except Exception:
                pass
        return FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    async def fake_probe(path):
        if "original.mp4" in path:
            return 12.5
        return 2.0
    monkeypatch.setattr("app.services.dubbing.pipeline.ffprobe_duration", fake_probe)
    monkeypatch.setattr("app.services.dubbing.ffmpeg.ffprobe_duration", fake_probe)
    monkeypatch.setattr("app.services.dubbing.alignment.ffprobe_duration", fake_probe)

    # Mock translate（不应被调用，因 resume）
    translate_called = []
    http_client = AsyncMock()

    async def fake_translate(*args, **kwargs):
        translate_called.append(True)
        return sample_translations
    monkeypatch.setattr("app.services.dubbing.pipeline.sf_translate", fake_translate)

    # Mock TTSService to write fake files instead of calling SiliconFlow
    mock_tts = AsyncMock()
    async def fake_synthesize(text, output_path, **kwargs):
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(b"FAKE_MP3")
    mock_tts.synthesize = fake_synthesize
    monkeypatch.setattr("app.services.dubbing.pipeline.TTSService", lambda: mock_tts)

    http_client.aclose = AsyncMock()

    progresses = []

    async def cb(p):
        progresses.append(p)

    result = await pl.run_dubbing_pipeline(
        video_id=777, video_path=video_path,
        work_base_dir=work_base,
        resume_from="translated",
        whisper_model="tiny",
        http_client=http_client,
        progress_callback=cb,
    )

    assert len(whisper_called) == 0  # 跳过了 Whisper
    assert len(translate_called) == 0  # 跳过了 translate
    assert result["segments_count"] == 5


# ── Test 4: scheduler chain 创建下一个 task ──

@pytest.mark.asyncio
async def test_scheduler_chain_creates_next_task(monkeypatch):
    """_handle_transcribe 成功后应创建 type=TRANSLATE 的 pending Task."""
    # Mock DB session
    from app.services import scheduler as sch_mod

    created_tasks = []

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def scalar_one_or_none(self):
            return self._rows[0] if self._rows else None

        def scalars(self):
            class _S:
                def __init__(self, rows):
                    self._rows = rows

                def all(self):
                    return self._rows
            return _S(self._rows)

    class FakeSession:
        def __init__(self, video_row=None, latest_task=None):
            self.video = video_row
            self.latest_task = latest_task
            self._next_id = [1000]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def execute(self, stmt):
            sql_str = str(stmt)
            if "SELECT" in sql_str.upper() and "videos" in sql_str.lower():
                return FakeResult([self.video])
            return FakeResult([])

        async def commit(self):
            pass

        async def refresh(self, obj):
            if not getattr(obj, "id", None):
                obj.id = self._next_id[0]
                self._next_id[0] += 1

        def add(self, obj):
            created_tasks.append(obj)

    # 直接测试 _create_next_task — 用真正的 async context manager
    from contextlib import asynccontextmanager

    fake_session_calls = []

    @asynccontextmanager
    async def fake_session_factory():
        s = FakeSession()
        fake_session_calls.append(s)
        yield s

    monkeypatch.setattr(sch_mod, "async_session_factory", fake_session_factory)
    monkeypatch.setattr(sch_mod, "_load_configs", AsyncMock(return_value={"download_dir": "./downloads"}))

    # ws_manager.broadcast mock
    async def fake_broadcast(msg):
        pass
    monkeypatch.setattr(sch_mod.ws_manager, "broadcast", fake_broadcast)

    next_id = await sch_mod._create_next_task(video_id=42, task_type="translate", message="测试")

    assert next_id > 0
    assert len(created_tasks) == 1
    assert created_tasks[0].type == "translate"
    assert created_tasks[0].status == "pending"
    assert created_tasks[0].video_id == 42
