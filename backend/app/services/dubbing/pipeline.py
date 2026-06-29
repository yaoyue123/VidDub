"""6 步主管线编排 (P4-40, paragraph-level refactor).

管线（per ADDENDUM pivot D-05，BGM 已弃用）：
1. extract_audio        — 提取 44.1kHz 立体声 WAV
2. whisper STT          — 本地 Whisper（per ADDENDUM D-17），返回 segments
3. translate            — SiliconFlow Qwen2.5-7B-Instruct，滑窗翻译（per-segment）
4. group + tts + align  — 按 ≥8s 静音分段 → paragraph TTS → paragraph 级 align
5. stitch               — 拼接整轨 dubbing.wav（paragraph 级，更少输入）
6. compose              — 替换原视频音轨 → final.mp4

每步通过 progress_callback 上报进度（WebSocket 或 CLI print）。
断点续跑：若 video.status 已是 transcribed/translated/synthesized，跳过已完成步骤。
"""
import asyncio
import json
import logging
import os
from typing import Any, Awaitable, Callable, Optional

import httpx

from app.services.siliconflow.client import get_async_client
from app.services.siliconflow.translate import translate_segments as sf_translate
from app.services.tts_new.service import TTSService
from app.services.dubbing.ffmpeg import extract_audio, extract_audio_mono_16k, ffprobe_duration, run_ffmpeg_async
from app.services.dubbing.alignment import align_segment, AlignResult
from app.services.dubbing.stitcher import build_dubbing_track
from app.services.dubbing.composer import compose_final_video
from app.services.dubbing.paths import video_file, video_work_dir, group_segments_by_silence
from app.core.storage import get_download_dir

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]


async def run_dubbing_pipeline(
    video_id: int,
    video_path: str,
    *,
    work_base_dir: str | None = None,
    resume_from: str = "",
    whisper_model: str = "tiny",
    whisper_language: str = "en",
    translation_model: str = "deepseek-ai/DeepSeek-V4-Flash",
    tts_model: str = "FunAudioLLM/CosyVoice2-0.5B",
    tts_voice: str = "anna",
    tts_speed: float = 1.0,
    tts_gain: float = 0.0,
    tts_format: str = "mp3",
    atempo_min: float = 0.7,
    atempo_max: float = 1.5,
    context_window: int = 2,
    progress_callback: Optional[ProgressCallback] = None,
    http_client: Optional[httpx.AsyncClient] = None,
) -> dict[str, Any]:
    """端到端运行 6 步管线，返回 {final_path, srt_path, segments_count}.

    Args:
        video_id: DB 中的视频 ID（用于确定工作目录 downloads/{video_id}/）
        video_path: 原视频文件路径
        work_base_dir: downloads 根目录
        resume_from: 跳过已完成步骤（"transcribed"/"translated"/"synthesized"）
        whisper_model: 本地 Whisper 模型名
        whisper_language: Whisper 强制语言（'en' 避免误识别）
        translation_model: SiliconFlow 翻译模型
        tts_model: SiliconFlow TTS 模型
        tts_voice: TTS 音色（不含 ':' 前缀，自动拼接）
        atempo_min/atempo_max: atempo 边界
        context_window: 翻译滑窗大小
        progress_callback: async 进度回调
        http_client: 可选共享 httpx 客户端（None 时内部创建）
    """
    work_base_dir = work_base_dir if work_base_dir is not None else get_download_dir()
    work_dir = video_work_dir(video_id, base_dir=work_base_dir)

    async def _emit(step: str, percent: float, **extra):
        if progress_callback:
            await progress_callback({"step": step, "percent": percent, **extra})

    # 探测视频时长（用于 dubbing.wav 总长对齐）
    video_duration = await ffprobe_duration(video_path)
    logger.info("video %d duration=%.2fs, work_dir=%s", video_id, video_duration, work_dir)

    own_client = False
    if http_client is None:
        http_client = get_async_client(timeout=120.0)
        own_client = True

    try:
        # ── Step 1: 提取音频 ──
        audio_path = video_file(video_id, "original_audio.wav", base_dir=work_base_dir)
        if not os.path.exists(audio_path):
            await _emit("extract_audio", 5, message="提取音频中...")
            await extract_audio(video_path, audio_path)
        await _emit("extract_audio", 10, audio_path=audio_path)

        # Whisper 用的 16kHz mono
        stt_audio_path = video_file(video_id, "original_audio_16k.wav", base_dir=work_base_dir)
        if not os.path.exists(stt_audio_path):
            await extract_audio_mono_16k(video_path, stt_audio_path)

        # ── Step 2: Whisper STT ──
        transcript_path = video_file(video_id, "transcript.json", base_dir=work_base_dir)
        if resume_from in ("", "pending", "downloading", "downloaded", "transcribing") or not os.path.exists(transcript_path):
            await _emit("transcribe", 15, message=f"Whisper 转写中 (model={whisper_model})...")
            segments = await _run_whisper(stt_audio_path, whisper_model, whisper_language)
            _save_json(transcript_path, segments)
        else:
            segments = _load_json(transcript_path)
        await _emit("transcribe", 30, segments_count=len(segments))

        if not segments:
            raise RuntimeError("Whisper 返回空 segments，无法继续")

        # ── Step 3: Translate ──
        translated_path = video_file(video_id, "translated.json", base_dir=work_base_dir)
        if resume_from in ("", "pending", "downloading", "downloaded", "transcribed") or not os.path.exists(translated_path):
            await _emit("translate", 35, message="SiliconFlow 翻译中...")
            translations = await sf_translate(
                http_client, segments,
                model=translation_model,
                context_window=context_window,
            )
            _save_json(translated_path, translations)
        else:
            translations = _load_json(translated_path)
        await _emit("translate", 50, translations_count=len(translations))

        # ── Step 4: TTS per paragraph + align ──
        aligned_dir = os.path.join(work_dir, "aligned")
        os.makedirs(aligned_dir, exist_ok=True)

        # Group segments into paragraphs (split on >=8s silence gaps)
        paragraphs = group_segments_by_silence(segments, threshold_sec=8.0)
        logger.info(
            "Grouped %d segments into %d paragraphs (threshold=8.0s)",
            len(segments), len(paragraphs),
        )

        aligned_files: list[dict[str, Any]] = []
        sem = asyncio.Semaphore(3)  # 并发限流 R4

        async def _process_paragraph(p: dict, merged_zh: str):
            async with sem:
                p_id = p["id"]
                tts_path = os.path.join(aligned_dir, f"paragraph_{p_id:03d}.{tts_format}")
                aligned_path = os.path.join(aligned_dir, f"paragraph_aligned_{p_id:03d}.wav")

                # Paragraph with all empty translations → generate silence
                if not merged_zh or not merged_zh.strip():
                    logger.warning(
                        "Paragraph %d has all empty translations, using silence", p_id,
                    )
                    if not os.path.exists(aligned_path):
                        dur = max(float(p["end"]) - float(p["start"]), 0.1)
                        await run_ffmpeg_async([
                            "ffmpeg", "-y",
                            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                            "-t", f"{dur:.3f}",
                            aligned_path,
                        ])
                    return {"aligned_path": aligned_path, "segment": p}

                if not os.path.exists(tts_path):
                    tts_service = TTSService()
                    await tts_service.synthesize(
                        text=merged_zh, output_path=tts_path,
                        model=tts_model, voice=tts_voice,
                        response_format=tts_format,
                        speed=tts_speed, gain=tts_gain,
                    )

                if not os.path.exists(aligned_path):
                    await _emit("synthesize", 50 + int(30 * p_id / max(len(paragraphs), 1)),
                                current=p_id + 1, total=len(paragraphs))
                    result: AlignResult = await align_segment(
                        tts_path, float(p["start"]), float(p["end"]),
                        aligned_path, atempo_min=atempo_min, atempo_max=atempo_max,
                    )
                    logger.info("paragraph %d aligned: ratio=%.2f action=%s", p_id, result.ratio, result.action)

                return {"aligned_path": aligned_path, "segment": p}

        # Build merged Chinese text per paragraph from per-segment translations
        tasks = []
        seg_idx = 0
        for p in paragraphs:
            n_segs = len(p["segments"])
            merged_zh = " ".join(
                translations[seg_idx + i]
                for i in range(n_segs)
                if seg_idx + i < len(translations) and translations[seg_idx + i].strip()
            )
            tasks.append(asyncio.create_task(_process_paragraph(p, merged_zh)))
            seg_idx += n_segs

        # CR-05: 用 asyncio.gather 替代 "create N tasks + 顺序 await"。
        try:
            results = await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        aligned_files.extend(results)
        await _emit("synthesize", 80, aligned_count=len(aligned_files))

        # ── Step 5: Stitch ──
        dubbing_path = video_file(video_id, "dubbing.wav", base_dir=work_base_dir)
        await _emit("stitch", 82, message="拼接整轨...")
        # Paragraphs carry start/end so stitcher places each at the correct time
        await build_dubbing_track(aligned_files, paragraphs, video_duration, dubbing_path)
        await _emit("stitch", 88, dubbing_path=dubbing_path)

        # ── Step 6: Compose ──
        file_stem = f"video_{video_id}"
        final_path = video_file(video_id, f"{file_stem}.mp4", base_dir=work_base_dir)
        await _emit("compose", 90, message="合成最终视频...")
        await compose_final_video(video_path, dubbing_path, final_path)

        # Bonus: SRT 字幕
        srt_path = video_file(video_id, f"{file_stem}.srt", base_dir=work_base_dir)
        _write_srt(segments, translations, srt_path)

        # Bonus: 双语字幕烧录版视频
        subtitled_path = video_file(video_id, f"{file_stem}_subtitled.mp4", base_dir=work_base_dir)
        try:
            from app.services.dubbing.subtitle_burn import (
                write_bilingual_ass,
                burn_subtitles_into_video,
            )
            ass_path = video_file(video_id, f"{file_stem}.ass", base_dir=work_base_dir)
            write_bilingual_ass(segments, translations, ass_path)
            await burn_subtitles_into_video(final_path, ass_path, subtitled_path)
            logger.info("Subtitled video generated: %s", subtitled_path)
        except Exception as e:
            logger.warning("Failed to generate subtitled video: %s", e)
            subtitled_path = None  # 烧录失败不阻塞主流程

        await _emit("compose", 100, final_path=final_path, srt_path=srt_path,
                    subtitled_path=subtitled_path)

        return {
            "final_path": final_path,
            "srt_path": srt_path,
            "dubbing_path": dubbing_path,
            "subtitled_path": subtitled_path,
            "segments_count": len(segments),
        }
    finally:
        if own_client:
            await http_client.aclose()


async def _run_whisper(audio_path: str, model_name: str, language: str) -> list[dict]:
    """调用本地 Whisper（per ADDENDUM D-17）."""
    from app.services.whisper_service import WhisperService
    svc = WhisperService(model_name=model_name)
    result = await svc.transcribe(audio_path, language=language, task="transcribe")
    # 转换为标准 segment 格式
    return [
        {
            "id": seg.get("id", i),
            "start": float(seg.get("start", 0.0)),
            "end": float(seg.get("end", 0.0)),
            "text": seg.get("text", "").strip(),
        }
        for i, seg in enumerate(result.get("segments", []))
    ]


def _save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_srt(segments: list[dict], translations: list[str], srt_path: str) -> None:
    """生成中文 SRT 字幕（时间戳沿用原 segments）."""
    from app.services.whisper_service import format_srt_timestamp

    lines: list[str] = []
    for i, seg in enumerate(segments):
        idx = i + 1
        start = format_srt_timestamp(float(seg.get("start", 0.0)))
        end = format_srt_timestamp(float(seg.get("end", 0.0)))
        text = translations[i] if i < len(translations) else seg.get("text", "")
        lines.append(str(idx))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
