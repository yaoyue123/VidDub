"""
Background task scheduler for video processing pipeline (Phase 4 重构).

任务流 (per D-13, D-14 + ADDENDUM)：
download → transcribe → translate → synthesize → compose → completed

每个步骤对应一个 Task；上一个成功后自动 chain 下一个 pending Task。
失败不级联（断点续跑靠 POST /api/dub/{id}/resume 或 CLI resume）。

WebSocket progress 通过 manager.broadcast 推送。
"""
import asyncio
import logging
import os
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.storage import get_download_dir
from app.core.websocket import manager as ws_manager
from app.models.video import Video
from app.models.task import Task
from app.models.config import Config
from app.models.subtitle import Subtitle
from app.models.enums import VideoStatus, TaskType, TaskStatus
from app.services.youtube import YoutubeService
logger = logging.getLogger(__name__)


# ── Progress helpers ──

def _make_progress_hook(task_id: int, video_id: int, db_session_factory) -> callable:
    """Create a yt-dlp progress hook for download tasks."""

    def progress_hook(d: dict[str, Any]) -> None:
        status = d.get("status", "")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            progress = (downloaded / total * 100) if total > 0 else 0
            speed = d.get("speed", 0)
            speed_str = f"{speed / 1024 / 1024:.1f} MB/s" if speed else "N/A"
            eta = d.get("eta", 0)
            eta_str = f"{eta}s" if eta else "N/A"

            async def _update():
                async with db_session_factory() as session:
                    await session.execute(
                        update(Task).where(Task.id == task_id).values(
                            progress=round(progress, 1),
                            message=f"下载中... {downloaded/1024/1024:.1f}MB / {total/1024/1024:.1f}MB ({speed_str}, ETA: {eta_str})",
                        )
                    )
                    await session.commit()

            try:
                asyncio.create_task(_update())
            except Exception:
                pass

            msg = {
                "type": "task_progress",
                "data": {
                    "task_id": task_id, "video_id": video_id,
                    "progress": round(progress, 1), "speed": speed_str,
                    "eta": eta_str, "status": "downloading",
                },
            }
            try:
                asyncio.create_task(ws_manager.broadcast(msg))
            except Exception:
                pass

        elif status == "finished":
            async def _finish():
                async with db_session_factory() as session:
                    await session.execute(
                        update(Task).where(Task.id == task_id)
                        .values(progress=100.0, message="下载完成，正在处理...")
                    )
                    await session.commit()

            try:
                asyncio.create_task(_finish())
            except Exception:
                pass

            msg = {
                "type": "task_progress",
                "data": {"task_id": task_id, "video_id": video_id, "progress": 100, "status": "finished"},
            }
            try:
                asyncio.create_task(ws_manager.broadcast(msg))
            except Exception:
                pass

        elif status == "error":
            error_msg = d.get("msg", "下载错误")

            async def _error():
                async with db_session_factory() as session:
                    await session.execute(
                        update(Task).where(Task.id == task_id)
                        .values(status=TaskStatus.FAILED, progress=0, message=error_msg, error_msg=error_msg)
                    )
                    await session.commit()

            try:
                asyncio.create_task(_error())
            except Exception:
                pass

    return progress_hook


async def _load_configs() -> dict[str, str]:
    """加载所有 config 表项."""
    async with async_session_factory() as session:
        result = await session.execute(select(Config))
        return {c.key: c.value for c in result.scalars().all()}


async def _create_next_task(video_id: int, task_type: str, message: str = "") -> int:
    """创建下一个 pending Task，返回 task_id."""
    async with async_session_factory() as session:
        task = Task(
            video_id=video_id,
            type=task_type,
            status=TaskStatus.PENDING,
            progress=0,
            message=message or f"等待 {task_type}...",
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        task_id = task.id

    await ws_manager.broadcast({
        "type": "task_created",
        "data": {"task_id": task_id, "video_id": video_id, "type": task_type, "status": TaskStatus.PENDING},
    })
    return task_id


class TaskScheduler:
    """Background task scheduler.

    Polls DB for pending tasks and dispatches them based on task.type.
    """

    HANDLERS = {
        TaskType.DOWNLOAD: "_handle_download",
        TaskType.TRANSCRIBE: "_handle_transcribe",
        TaskType.TRANSLATE: "_handle_translate",
        TaskType.SYNTHESIZE: "_handle_synthesize",
        TaskType.COMPOSE: "_handle_compose",
        # 兼容旧任务类型
        "upload_bilibili": "_handle_upload_bilibili",
        "upload_xigua": "_handle_upload_xigua",
        # 旧 dub 一体化（已拆分为新 chain，仍保留兼容）
        "dub": "_handle_dub_legacy",
    }

    def __init__(
        self,
        download_dir: str | None = None,
        max_concurrent: int = 3,
        poll_interval: float = 2.0,
        max_resolution: int = 1080,
    ):
        self.download_dir = download_dir if download_dir is not None else get_download_dir()
        self.max_concurrent = max_concurrent
        self.poll_interval = poll_interval
        self.max_resolution = max_resolution

        self._yt_service = YoutubeService(
            download_dir=download_dir, max_resolution=max_resolution,
        )
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running_tasks: dict[int, asyncio.Task] = {}
        self._poll_task: Optional[asyncio.Task] = None
        self._running = False
        # Phase 6: 平台登录态定期检测
        self._platform_check_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        # Phase 6: 启动登录态检测循环（每 30 分钟）
        self._platform_check_task = asyncio.create_task(self._platform_check_loop())
        logger.info("TaskScheduler started (max_concurrent=%d, poll=%.1fs)",
                    self.max_concurrent, self.poll_interval)

    async def stop(self) -> None:
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        # Phase 6: 停止平台登录态检测
        if self._platform_check_task:
            self._platform_check_task.cancel()
            try:
                await self._platform_check_task
            except asyncio.CancelledError:
                pass
            self._platform_check_task = None

        for tid, task in list(self._running_tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            async with async_session_factory() as session:
                await session.execute(
                    update(Task).where(Task.id == tid).values(status=TaskStatus.CANCELLED, message="调度器关闭")
                )
                await session.commit()
        self._running_tasks.clear()
        logger.info("TaskScheduler stopped")

    # ── Poll loop ──

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self._poll_once()
            except Exception as e:
                logger.error("Poll error: %s", e, exc_info=True)
            await asyncio.sleep(self.poll_interval)

    async def _poll_once(self) -> None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Task).where(Task.status == TaskStatus.PENDING)
                .order_by(Task.created_at.asc())
                .limit(self.max_concurrent)
            )
            pending = result.scalars().all()

        for task in pending:
            if task.id in self._running_tasks:
                continue
            self._running_tasks[task.id] = asyncio.create_task(
                self._dispatch(task.id, task.video_id, task.type)
            )

    # ── Phase 6: 平台登录态定期检测 ──

    async def _platform_check_loop(self) -> None:
        """每 30 分钟检测一次各平台登录态，过期则推送 WS 事件."""
        from app.services.platform.base import LOGIN_CHECK_INTERVAL_SEC
        from app.services.platform.manager import get_login_manager
        await asyncio.sleep(60)  # 启动后 1 分钟才首次检测，等服务就绪
        while self._running:
            try:
                manager = get_login_manager()
                for pf in manager.SUPPORTED_PLATFORMS:
                    state = manager.load_storage_state(pf)
                    if not state:
                        continue
                    try:
                        login = manager.get(pf)
                        logged_in = await login.check_login_status()
                        if not logged_in:
                            logger.info("Platform %s login expired (scheduler check)", pf)
                            await ws_manager.broadcast({
                                "type": "platform_login_expired",
                                "data": {"platform": pf},
                            })
                    except Exception as e:
                        logger.warning("Platform %s check failed: %s", pf, e)
            except Exception as e:
                logger.error("platform_check_loop error: %s", e, exc_info=True)
            await asyncio.sleep(LOGIN_CHECK_INTERVAL_SEC)

    # ── Dispatch ──

    async def _dispatch(self, task_id: int, video_id: int, task_type: str) -> None:
        async with self._semaphore:
            try:
                handler_name = self.HANDLERS.get(task_type)
                if not handler_name:
                    logger.warning("Unknown task type: %s (task_id=%d)", task_type, task_id)
                    async with async_session_factory() as session:
                        await session.execute(
                            update(Task).where(Task.id == task_id)
                            .values(status=TaskStatus.FAILED, error_msg=f"未知任务类型: {task_type}")
                        )
                        await session.commit()
                    return

                handler = getattr(self, handler_name)
                await handler(task_id, video_id)
            except asyncio.CancelledError:
                logger.info("Task %d cancelled", task_id)
                raise
            except Exception as e:
                logger.error("Task %d failed: %s", task_id, e, exc_info=True)
                async with async_session_factory() as session:
                    await session.execute(
                        update(Task).where(Task.id == task_id)
                        .values(status=TaskStatus.FAILED, error_msg=str(e))
                    )
                    await session.execute(
                        update(Video).where(Video.id == video_id)
                        .values(status=VideoStatus.FAILED)
                    )
                    await session.commit()
                await ws_manager.broadcast({
                    "type": "task_error",
                    "data": {"task_id": task_id, "video_id": video_id, "error": str(e)},
                })
            finally:
                self._running_tasks.pop(task_id, None)

    # ── DOWNLOAD ──

    async def _handle_download(self, task_id: int, video_id: int) -> None:
        """下载视频 + 末尾自动创建 transcribe Task."""
        configs = await _load_configs()
        download_dir = get_download_dir()

        async with async_session_factory() as session:
            await session.execute(
                update(Task).where(Task.id == task_id)
                .values(status=TaskStatus.RUNNING, progress=0, message="准备下载...")
            )
            await session.execute(
                update(Video).where(Video.id == video_id).values(status=VideoStatus.DOWNLOADING)
            )
            await session.commit()

        await ws_manager.broadcast({
            "type": "task_start",
            "data": {"task_id": task_id, "video_id": video_id, "type": TaskType.DOWNLOAD},
        })

        async with async_session_factory() as session:
            v = (await session.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
        if not v:
            raise ValueError(f"Video {video_id} not found")

        hook = _make_progress_hook(task_id, video_id, async_session_factory)
        filepath = await self._yt_service.download(v.youtube_url, progress_hook=hook)

        if not filepath:
            raise RuntimeError("下载失败，请检查网络或视频链接")

        # 把视频复制/重命名到 downloads/{video_id}/original.mp4（D-15 约定）
        from app.services.dubbing.paths import video_file, video_work_dir
        work_dir = video_work_dir(video_id, base_dir=download_dir)
        original_path = video_file(video_id, "original.mp4", base_dir=download_dir)
        if os.path.abspath(filepath) != os.path.abspath(original_path):
            import shutil
            shutil.copy2(filepath, original_path)

        async with async_session_factory() as session:
            await session.execute(
                update(Task).where(Task.id == task_id)
                .values(status=TaskStatus.COMPLETED, progress=100.0, message="下载完成")
            )
            await session.execute(
                update(Video).where(Video.id == video_id)
                .values(status=VideoStatus.DOWNLOADED, filepath=original_path)
            )
            await session.commit()

        await ws_manager.broadcast({
            "type": "task_complete",
            "data": {"task_id": task_id, "video_id": video_id, "filepath": original_path},
        })

        # 自动 chain：创建 transcribe Task
        await _create_next_task(video_id, TaskType.TRANSCRIBE, "等待转写...")

    # ── TRANSCRIBE (local Whisper, per ADDENDUM D-17) ──

    async def _handle_transcribe(self, task_id: int, video_id: int) -> None:
        configs = await _load_configs()

        async with async_session_factory() as session:
            await session.execute(
                update(Task).where(Task.id == task_id)
                .values(status=TaskStatus.RUNNING, progress=0, message="Whisper 转写中...")
            )
            # WR-07: 不再复用 DOWNLOADING（与 D-13 状态机冲突），改用 TRANSCRIBING 表示
            # Whisper STT 进行中。
            await session.execute(
                update(Video).where(Video.id == video_id).values(status=VideoStatus.TRANSCRIBING)
            )
            await session.commit()

        await ws_manager.broadcast({
            "type": "task_start",
            "data": {"task_id": task_id, "video_id": video_id, "type": TaskType.TRANSCRIBE},
        })

        async with async_session_factory() as session:
            v = (await session.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
        if not v or not v.filepath:
            raise ValueError(f"Video {video_id} or filepath missing")

        # Optional: 背景音分离 (demucs) → 用分离后的人声轨转录，更准确
        from app.services.dubbing.paths import video_file, video_work_dir
        work_base = get_download_dir()
        work_dir = video_work_dir(video_id, base_dir=work_base)
        bg_sep_enabled = configs.get("background_separation_enabled", "false").lower() in ("true", "1", "yes")
        vocals_path = video_file(video_id, "vocals.wav", base_dir=work_base)

        if bg_sep_enabled and not os.path.exists(vocals_path):
            try:
                from app.services.dubbing.audio_separation import separate_audio
                original_audio = video_file(video_id, "original_audio.wav", base_dir=work_base)
                if not os.path.exists(original_audio):
                    from app.services.dubbing.ffmpeg import extract_audio
                    await extract_audio(v.filepath, original_audio)
                sep_device = configs.get("separation_device", "cpu")
                sep_model = configs.get("separation_model", "htdemucs")
                await separate_audio(
                    original_audio, os.path.join(work_dir, "separated"),
                    model=sep_model, device=sep_device,
                )
                logger.info("Background separation complete for video %d", video_id)
            except Exception as e:
                logger.warning("Background separation failed for video %d: %s", video_id, e)

        # 调用本地 Whisper（优先用人声轨，转录更准确）
        whisper_model = configs.get("whisper_model", "tiny")
        whisper_language = configs.get("whisper_language", "en")
        from app.services.whisper_service import WhisperService
        svc = WhisperService(model_name=whisper_model)

        # Prefer vocals.wav (clean speech) if available, else fall back to original
        stt_audio = video_file(video_id, "original_audio_16k.wav", base_dir=work_base)
        if os.path.exists(vocals_path):
            # Extract 16k mono from clean vocals for better STT accuracy
            stt_audio = video_file(video_id, "vocals_16k.wav", base_dir=work_base)
            if not os.path.exists(stt_audio):
                from app.services.dubbing.ffmpeg import extract_audio_mono_16k
                await extract_audio_mono_16k(vocals_path, stt_audio)
        elif not os.path.exists(stt_audio):
            from app.services.dubbing.ffmpeg import extract_audio_mono_16k
            await extract_audio_mono_16k(v.filepath, stt_audio)

        result = await svc.transcribe(stt_audio, language=whisper_language, task="transcribe")
        segments = [
            {"id": seg.get("id", i), "start": float(seg.get("start", 0)), "end": float(seg.get("end", 0)),
             "text": seg.get("text", "").strip(),
             "no_speech_prob": float(seg.get("no_speech_prob", 0.0))}
            for i, seg in enumerate(result.get("segments", []))
        ]
        import json
        transcript_path = video_file(video_id, "transcript.json", base_dir=get_download_dir())
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(segments, f, ensure_ascii=False, indent=2)

        # ── Voice cloning: extract + upload sample during transcribe ──
        voice_clone_enabled = configs.get("voice_clone_enabled", "false").lower() in ("true", "1", "yes")
        extract_during_transcribe = configs.get("extract_voice_sample_during_transcribe", "false").lower() in ("true", "1", "yes")

        if voice_clone_enabled and extract_during_transcribe and segments:
            try:
                # Determine audio source: prefer vocals.wav, fall back to original_audio.wav
                clone_source = None
                if os.path.exists(vocals_path):
                    clone_source = vocals_path
                else:
                    orig_audio = video_file(video_id, "original_audio.wav", base_dir=work_base)
                    if os.path.exists(orig_audio):
                        clone_source = orig_audio

                if clone_source:
                    from app.services.dubbing.voice_cloner import _extract_speech_sample
                    sample_info = _extract_speech_sample(
                        vocals_path, segments, video_id, work_base,
                        audio_path=clone_source,
                    )
                    if sample_info:
                        sample_path, sample_text = sample_info
                        from app.services.voice_cloner.siliconflow_provider import (
                            SiliconFlowVoiceCloner,
                        )
                        cloner = SiliconFlowVoiceCloner()
                        voice_name = f"video_{video_id}_speaker"
                        cloned_uri = await cloner.upload_voice(
                            sample_path, voice_name, sample_text,
                        )
                        if cloned_uri:
                            async with async_session_factory() as ss:
                                await ss.execute(
                                    update(Video).where(Video.id == video_id).values(
                                        cloned_voice_uri=cloned_uri,
                                        cloned_voice_name=voice_name,
                                        voice_selection_method="cloned",
                                    )
                                )
                                await ss.commit()
                            logger.info(
                                "Voice cloned during transcribe for video %d: %s",
                                video_id, cloned_uri,
                            )
            except Exception as e:
                logger.warning(
                    "Voice clone during transcribe failed (non-blocking) for video %d: %s",
                    video_id, e,
                )

        async with async_session_factory() as session:
            await session.execute(
                update(Task).where(Task.id == task_id)
                .values(status=TaskStatus.COMPLETED, progress=100.0,
                        message=f"转写完成 ({len(segments)} 段)")
            )
            await session.execute(
                update(Video).where(Video.id == video_id).values(status=VideoStatus.TRANSCRIBED)
            )
            await session.commit()

        await ws_manager.broadcast({
            "type": "task_complete",
            "data": {"task_id": task_id, "video_id": video_id, "segments": len(segments)},
        })

        await _create_next_task(video_id, TaskType.TRANSLATE, "等待翻译...")

    # ── TRANSLATE ──

    async def _handle_translate(self, task_id: int, video_id: int) -> None:
        configs = await _load_configs()
        backend = configs.get("translation_backend", "siliconflow")

        async with async_session_factory() as session:
            await session.execute(
                update(Task).where(Task.id == task_id)
                .values(status=TaskStatus.RUNNING, progress=0, message=f"{backend} 翻译中...")
            )
            await session.execute(
                update(Video).where(Video.id == video_id).values(status=VideoStatus.TRANSCRIBED)
            )
            await session.commit()

        await ws_manager.broadcast({
            "type": "task_start",
            "data": {"task_id": task_id, "video_id": video_id, "type": TaskType.TRANSLATE},
        })

        from app.services.dubbing.paths import video_file
        work_base = get_download_dir()
        transcript_path = video_file(video_id, "transcript.json", base_dir=work_base)

        import json
        with open(transcript_path, "r", encoding="utf-8") as f:
            segments = json.load(f)

        from app.services.translator.service import TranslationService
        translation_svc = TranslationService()
        translation_model = configs.get("translation_model", "deepseek-ai/DeepSeek-V4-Flash")
        context_window = int(configs.get("translation_context_window", "2"))

        translations = await translation_svc.translate_segments(
            segments,
            source_lang="English",
            target_lang="Chinese",
            model=translation_model,
            context_window=context_window,
        )

        translated_path = video_file(video_id, "translated.json", base_dir=work_base)
        with open(translated_path, "w", encoding="utf-8") as f:
            json.dump(translations, f, ensure_ascii=False, indent=2)

        async with async_session_factory() as session:
            await session.execute(
                update(Task).where(Task.id == task_id)
                .values(status=TaskStatus.COMPLETED, progress=100.0,
                        message=f"翻译完成 ({len(translations)} 段)")
            )
            await session.execute(
                update(Video).where(Video.id == video_id).values(status=VideoStatus.TRANSLATED)
            )
            await session.commit()

        await ws_manager.broadcast({
            "type": "task_complete",
            "data": {"task_id": task_id, "video_id": video_id, "segments": len(translations)},
        })

        await _create_next_task(video_id, TaskType.SYNTHESIZE, "等待配音合成...")

    # ── SYNTHESIZE (TTS + align per paragraph, grouped on >=8s silence) ──

    async def _handle_synthesize(self, task_id: int, video_id: int) -> None:
        configs = await _load_configs()

        async with async_session_factory() as session:
            await session.execute(
                update(Task).where(Task.id == task_id)
                .values(status=TaskStatus.RUNNING, progress=0, message="TTS 合成中...")
            )
            await session.execute(
                update(Video).where(Video.id == video_id).values(status=VideoStatus.TRANSLATED)
            )
            await session.commit()

        await ws_manager.broadcast({
            "type": "task_start",
            "data": {"task_id": task_id, "video_id": video_id, "type": TaskType.SYNTHESIZE},
        })

        from app.services.dubbing.paths import video_file, video_work_dir, group_segments_by_silence
        work_base = get_download_dir()
        transcript_path = video_file(video_id, "transcript.json", base_dir=work_base)
        translated_path = video_file(video_id, "translated.json", base_dir=work_base)

        import json
        with open(transcript_path, "r", encoding="utf-8") as f:
            segments = json.load(f)
        with open(translated_path, "r", encoding="utf-8") as f:
            translations = json.load(f)

        from app.services.tts_new.service import TTSService
        from app.services.dubbing.alignment import align_segment
        from app.services.dubbing.ffmpeg import ffprobe_duration

        tts_model = configs.get("tts_model", "FunAudioLLM/CosyVoice2-0.5B")
        tts_voice = configs.get("tts_voice_simple", configs.get("tts_voice", "anna"))
        # 去掉旧格式 "Model:voice" 前缀（兼容）
        if ":" in tts_voice:
            tts_voice = tts_voice.split(":")[-1]

        # ── Auto voice cloning / auto voice selection ──
        voice_clone_enabled = configs.get("voice_clone_enabled", "false").lower() in ("true", "1", "yes")
        voice_selection = "default"
        cloned_uri: Optional[str] = None
        vocals_path = video_file(video_id, "vocals.wav", base_dir=work_base)

        # Check if a cloned voice already exists (from transcribe stage, Phase 12)
        existing_cloned_uri: Optional[str] = None
        try:
            async with async_session_factory() as ss:
                v = (await ss.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
                if v and v.cloned_voice_uri:
                    existing_cloned_uri = v.cloned_voice_uri
        except Exception:
            pass

        if existing_cloned_uri:
            # Use existing cloned voice from transcribe stage
            tts_voice = existing_cloned_uri
            cloned_uri = existing_cloned_uri
            voice_selection = "cloned"
            logger.info("Using pre-cloned voice for video %d: %s", video_id, existing_cloned_uri)
        elif voice_clone_enabled and os.path.exists(vocals_path):
            # Try voice cloning from the separated vocals (original behavior)
            try:
                from app.services.dubbing.voice_cloner import clone_voice_from_vocals
                clone_result = await clone_voice_from_vocals(
                    vocals_path, segments, video_id, base_dir=work_base,
                )
                if clone_result:
                    tts_voice = clone_result["voice"]
                    cloned_uri = clone_result["uri"]
                    voice_selection = "cloned"
                    logger.info("Using cloned voice for video %d: %s", video_id, tts_voice)
            except Exception as e:
                logger.warning("Voice cloning failed for video %d: %s", video_id, e)

        if voice_selection == "default":
            # Auto-select voice based on pitch analysis
            auto_voice_enabled = configs.get("auto_voice_selection_enabled", "true").lower() in ("true", "1", "yes")
            if auto_voice_enabled:
                try:
                    from app.services.dubbing.voice_cloner import auto_select_voice
                    analysis_audio = vocals_path if os.path.exists(vocals_path) else (
                        video_file(video_id, "original_audio.wav", base_dir=work_base)
                    )
                    if os.path.exists(analysis_audio):
                        tts_voice = auto_select_voice(
                            analysis_audio, segments, default_voice=tts_voice,
                        )
                        voice_selection = "auto_pitch"
                except Exception as e:
                    logger.debug("Auto voice selection failed, using default: %s", e)

        # Persist voice selection metadata
        if voice_selection != "default":
            try:
                async with async_session_factory() as session:
                    await session.execute(
                        update(Video).where(Video.id == video_id).values(
                            cloned_voice_uri=cloned_uri,
                            cloned_voice_name=f"video_{video_id}_speaker" if cloned_uri else None,
                            voice_selection_method=voice_selection,
                        )
                    )
                    await session.commit()
            except Exception as e:
                logger.debug("Failed to persist voice metadata: %s", e)

        tts_speed = float(configs.get("tts_speed", "1.0"))
        tts_gain = float(configs.get("tts_gain", "0"))
        tts_format = configs.get("tts_format", "mp3")
        atempo_min = float(configs.get("atempo_min", "0.7"))
        atempo_max = float(configs.get("atempo_max", "1.5"))

        work_dir = video_work_dir(video_id, base_dir=work_base)
        aligned_dir = os.path.join(work_dir, "aligned")
        os.makedirs(aligned_dir, exist_ok=True)

        video_duration = await ffprobe_duration(
            video_file(video_id, "original.mp4", base_dir=work_base)
        )

        # Group segments into paragraphs (split on >=8s silence gaps)
        paragraphs = group_segments_by_silence(segments, threshold_sec=8.0)
        logger.info(
            "Grouped %d segments into %d paragraphs (threshold=8.0s)",
            len(segments), len(paragraphs),
        )

        aligned_files = []
        sem = asyncio.Semaphore(3)

        async def _one_paragraph(p: dict, merged_zh: str):
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
                        from app.services.dubbing.ffmpeg import run_ffmpeg_async
                        await run_ffmpeg_async([
                            "ffmpeg", "-y",
                            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                            "-t", f"{dur:.3f}",
                            aligned_path,
                        ])
                    return {"aligned_path": aligned_path, "segment": p}

                # Idempotency: skip TTS if output already exists
                if not os.path.exists(tts_path):
                    tts_service = TTSService()
                    await tts_service.synthesize(
                        text=merged_zh, output_path=tts_path,
                        model=tts_model, voice=tts_voice,
                        response_format=tts_format, speed=tts_speed, gain=tts_gain,
                    )
                if not os.path.exists(aligned_path):
                    await align_segment(
                        tts_path, float(p["start"]), float(p["end"]), aligned_path,
                        atempo_min=atempo_min, atempo_max=atempo_max,
                    )
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
            tasks.append(asyncio.create_task(_one_paragraph(p, merged_zh)))
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

        # Stitch — paragraphs carry start/end so stitcher places them correctly
        from app.services.dubbing.stitcher import build_dubbing_track
        dubbing_path = video_file(video_id, "dubbing.wav", base_dir=work_base)
        await build_dubbing_track(aligned_files, paragraphs, video_duration, dubbing_path)

        async with async_session_factory() as session:
            await session.execute(
                update(Task).where(Task.id == task_id)
                .values(status=TaskStatus.COMPLETED, progress=100.0,
                        message=f"合成完成 ({len(aligned_files)} 段落)")
            )
            await session.execute(
                update(Video).where(Video.id == video_id).values(status=VideoStatus.SYNTHESIZED)
            )
            await session.commit()

        await ws_manager.broadcast({
            "type": "task_complete",
            "data": {"task_id": task_id, "video_id": video_id, "segments": len(aligned_files)},
        })

        # Generate AI title/metadata BEFORE compose so translated title is available
        # for output file naming.
        try:
            tg_enabled = configs.get("title_generator_enabled", "true").lower() in ("true", "1", "yes")
            if tg_enabled:
                logger.info("Phase 8: generating AI title candidates for video %d", video_id)
                await self._handle_generate_title(video_id)
        except Exception as e:
            logger.warning("title generation trigger failed: %s", e)

        await _create_next_task(video_id, TaskType.COMPOSE, "等待视频合成...")

    # ── COMPOSE ──

    async def _handle_compose(self, task_id: int, video_id: int) -> None:
        work_base = get_download_dir()
        configs = await _load_configs()

        async with async_session_factory() as session:
            await session.execute(
                update(Task).where(Task.id == task_id)
                .values(status=TaskStatus.RUNNING, progress=0, message="合成视频中...")
            )
            await session.execute(
                update(Video).where(Video.id == video_id).values(status=VideoStatus.SYNTHESIZED)
            )
            await session.commit()

        await ws_manager.broadcast({
            "type": "task_start",
            "data": {"task_id": task_id, "video_id": video_id, "type": TaskType.COMPOSE},
        })

        from app.services.dubbing.paths import video_file, sanitize_filename
        from app.services.dubbing.composer import compose_final_video
        from app.services.dubbing.pipeline import _write_srt

        original_video = video_file(video_id, "original.mp4", base_dir=work_base)
        dubbing_audio = video_file(video_id, "dubbing.wav", base_dir=work_base)

        # Resolve a descriptive filename stem from DB metadata
        file_stem = "final"  # fallback
        async with async_session_factory() as session:
            v = (await session.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
            if v:
                candidate = (v.title_chosen or v.title_zh or v.title or "").strip()
                file_stem = sanitize_filename(candidate) or f"video_{video_id}"

        final_path = video_file(video_id, f"{file_stem}.mp4", base_dir=work_base)
        srt_path = video_file(video_id, f"{file_stem}.srt", base_dir=work_base)
        subtitled_path = video_file(video_id, f"{file_stem}_subtitled.mp4", base_dir=work_base)

        # If background audio was separated, mix it back in (preserves BGM/sfx)
        background_path = video_file(video_id, "background.wav", base_dir=work_base)
        if not os.path.exists(background_path):
            # Try the demucs output path
            from app.services.dubbing.paths import video_work_dir
            demucs_bg = os.path.join(
                video_work_dir(video_id, base_dir=work_base),
                "separated", "htdemucs",
                os.path.splitext(os.path.basename(
                    video_file(video_id, "original_audio.wav", base_dir=work_base)
                ))[0],
                "background.wav",
            )
            if os.path.exists(demucs_bg):
                background_path = demucs_bg

        if os.path.exists(background_path):
            from app.services.dubbing.audio_separation import mix_background_audio
            from app.services.dubbing.ffmpeg import run_ffmpeg_async
            bg_volume = float(configs.get("background_volume", "0.3"))
            mixed_dubbing = video_file(video_id, "dubbing_mixed.wav", base_dir=work_base)
            mix_cmd = mix_background_audio(
                dubbing_audio, background_path, mixed_dubbing,
                background_volume=bg_volume,
            )
            await run_ffmpeg_async(mix_cmd)
            compose_audio = mixed_dubbing
            logger.info("Background mixed: volume=%.2f", bg_volume)
        else:
            compose_audio = dubbing_audio

        await compose_final_video(original_video, compose_audio, final_path)

        # 写 SRT (中文翻译版)
        import json
        with open(video_file(video_id, "transcript.json", base_dir=work_base), "r", encoding="utf-8") as f:
            segments = json.load(f)
        with open(video_file(video_id, "translated.json", base_dir=work_base), "r", encoding="utf-8") as f:
            translations = json.load(f)
        _write_srt(segments, translations, srt_path)

        # 读取 SRT 内容
        srt_content = ""
        if os.path.exists(srt_path):
            with open(srt_path, "r", encoding="utf-8") as f:
                srt_content = f.read()

        # 生成原始语言 SRT（用 segments 的原始 text）
        from app.services.whisper_service import format_srt_timestamp
        original_srt_lines = []
        for i, seg in enumerate(segments):
            original_srt_lines.append(str(i + 1))
            original_srt_lines.append(
                f"{format_srt_timestamp(float(seg.get('start', 0.0)))} --> {format_srt_timestamp(float(seg.get('end', 0.0)))}"
            )
            original_srt_lines.append(seg.get("text", "").strip())
            original_srt_lines.append("")
        original_srt_content = "\n".join(original_srt_lines)

        # 生成双语字幕烧录版视频（受 subtitle_enabled 配置控制）
        subtitle_enabled = configs.get("subtitle_enabled", "true").lower() in ("true", "1", "yes")
        if subtitle_enabled:
            try:
                from app.services.dubbing.subtitle_burn import (
                    write_bilingual_ass,
                    burn_subtitles_into_video,
                )
                sub_font_size = max(int(configs.get("subtitle_font_size", "20")), 12)
                sub_position = configs.get("subtitle_position", "bottom")
                ass_path = video_file(video_id, "bilingual.ass", base_dir=work_base)
                write_bilingual_ass(segments, translations, ass_path,
                                    font_size=sub_font_size, position=sub_position)
                await burn_subtitles_into_video(final_path, ass_path, subtitled_path)
                logger.info("Subtitled video generated: %s", subtitled_path)
            except Exception as e:
                logger.warning("Failed to generate subtitled video: %s", e)
                subtitled_path = None  # 烧录失败不阻塞主流程
        else:
            subtitled_path = None
            logger.info("Subtitle burning disabled by config")

        async with async_session_factory() as session:
            # 保存翻译字幕
            existing_zh = await session.execute(
                select(Subtitle).where(
                    Subtitle.video_id == video_id,
                    Subtitle.language == "zh",
                    Subtitle.source == "translation",
                )
            )
            zh_sub = existing_zh.scalar_one_or_none()
            if zh_sub:
                zh_sub.content = srt_content
                zh_sub.filepath = srt_path
            else:
                session.add(Subtitle(
                    video_id=video_id, language="zh", source="translation",
                    content=srt_content, filepath=srt_path,
                ))

            # 保存原始语言字幕 (v3.2: 统一 DB 存储)
            existing_orig = await session.execute(
                select(Subtitle).where(
                    Subtitle.video_id == video_id,
                    Subtitle.language == "original",
                    Subtitle.source == "whisper",
                )
            )
            orig_sub = existing_orig.scalar_one_or_none()
            if orig_sub:
                orig_sub.content = original_srt_content
            else:
                session.add(Subtitle(
                    video_id=video_id, language="original", source="whisper",
                    content=original_srt_content,
                ))

            await session.execute(
                update(Task).where(Task.id == task_id)
                .values(status=TaskStatus.COMPLETED, progress=100.0,
                        message=f"合成完成 {os.path.basename(final_path)}")
            )
            db_update_values = {
                "status": VideoStatus.COMPLETED,
                "dubbed_filepath": final_path,
                "dubbed_subtitled_filepath": subtitled_path,
            }
            await session.execute(
                update(Video).where(Video.id == video_id).values(**db_update_values)
            )
            await session.commit()

        await ws_manager.broadcast({
            "type": "task_complete",
            "data": {
                "task_id": task_id, "video_id": video_id,
                "final_path": final_path, "srt_path": srt_path,
                "subtitled_path": subtitled_path,
            },
        })

        # Phase 7: auto publish (title metadata already generated before compose)
        try:
            auto_pub = configs.get("auto_publish_enabled", "true").lower() in ("true", "1", "yes")
            if auto_pub:
                logger.info("Auto-publish trigger for video %d (compose done)", video_id)
                asyncio.create_task(self._handle_publish(video_id))
        except Exception as e:
            logger.warning("auto_publish trigger failed: %s", e)

    # ── Phase 7: publish handler (D7-08) ──

    async def _handle_publish(self, video_id: int) -> None:
        """配音完成后自动发布到所有平台.

        与 download/transcribe 等 _handle_xxx 不同：
        - 不操作 Task 表（发布是 best-effort，不阻塞主 chain）
        - 失败记录在 publish_records 表，由 API / UI 单独展示
        """
        try:
            from app.services.publish.manager import get_publish_manager
            pm = get_publish_manager()
            await pm.auto_publish(video_id=video_id)
        except Exception as e:
            logger.error("Auto-publish for video %d failed: %s", video_id, e, exc_info=True)

    # ── Phase 8: AI title generator handler (D8-04, D8-05) ──

    async def _handle_generate_title(self, video_id: int) -> None:
        """Generate AI title candidates + rich metadata via SiliconFlow.

        Populates: ai_title_candidates, ai_tags_candidates (legacy),
        plus title_zh, tags_zh, description_zh, title_en, description_en.

        Called BEFORE compose so translated title is available for output
        file naming. Failure is non-blocking (log warning + return).
        """
        import json as _json
        configs = await _load_configs()

        async with async_session_factory() as session:
            v = (await session.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
            if not v:
                logger.warning("generate_title: video %d not found", video_id)
                return
            # Snapshot original metadata before we leave the session
            original_title = v.title or ""
            original_desc = v.description or ""

        try:
            from app.services.title_generator import generate_title_candidates
            result = await generate_title_candidates(
                v,
                configs=configs,
                num_titles=int(configs.get("title_generator_candidate_count", "5")),
                num_tags=int(configs.get("title_generator_tag_count", "8")),
            )
        except Exception as e:
            logger.warning("generate_title for video %d failed: %s (publish will fallback)", video_id, e)
            return

        titles = result.get("titles") or []
        tags = result.get("tags") or []
        summary_zh = result.get("summary_zh") or ""

        if not titles and not tags:
            logger.warning("generate_title video %d returned empty candidates", video_id)
            return

        # Best-guess translated title: first candidate (user can override via title_chosen)
        title_zh = titles[0] if titles else None

        try:
            async with async_session_factory() as session:
                await session.execute(
                    update(Video).where(Video.id == video_id).values(
                        # Legacy candidate fields
                        ai_title_candidates=_json.dumps(titles, ensure_ascii=False) if titles else None,
                        ai_tags_candidates=_json.dumps(tags, ensure_ascii=False) if tags else None,
                        # Rich metadata for upload/publishing
                        title_zh=title_zh,
                        title_en=original_title or None,
                        tags_zh=_json.dumps(tags, ensure_ascii=False) if tags else None,
                        description_zh=summary_zh or None,
                        description_en=original_desc or None,
                    )
                )
                await session.commit()
            logger.info(
                "Phase 8: video %d metadata saved (title_zh=%s, %d titles, %d tags, summary=%d chars)",
                video_id, title_zh, len(titles), len(tags), len(summary_zh),
            )
            await ws_manager.broadcast({
                "type": "ai_title_ready",
                "data": {"video_id": video_id, "titles": len(titles), "tags": len(tags)},
            })
        except Exception as e:
            logger.warning("generate_title persist failed for video %d: %s", video_id, e)

    # ── Legacy upload handlers (unchanged from Phase 3) ──

    async def _handle_dub_legacy(self, task_id: int, video_id: int) -> None:
        """旧 'dub' 任务类型 — 一体化执行 translate+synthesize+compose.
        Phase 4 改用 chain (translate→synthesize→compose)，此 handler 仅兼容旧 API.
        """
        # 简化：直接 chain 创建下一个 translate Task
        logger.info("Legacy 'dub' task %d → creating translate chain", task_id)
        async with async_session_factory() as session:
            await session.execute(
                update(Task).where(Task.id == task_id)
                .values(status=TaskStatus.COMPLETED, progress=100.0, message="转交新 chain 处理")
            )
            await session.commit()
        await _create_next_task(video_id, TaskType.TRANSLATE, "等待翻译...")

    async def _handle_upload_bilibili(self, task_id: int, video_id: int) -> None:
        async with async_session_factory() as session:
            await session.execute(
                update(Task).where(Task.id == task_id)
                .values(status=TaskStatus.RUNNING, progress=0, message="准备上传 Bilibili...")
            )
            await session.execute(
                update(Video).where(Video.id == video_id).values(status=VideoStatus.COMPLETED)
            )
            await session.commit()
        # 上传逻辑沿用 Phase 3 实现（略 — Phase 4 不涉及）

    async def _handle_upload_xigua(self, task_id: int, video_id: int) -> None:
        async with async_session_factory() as session:
            await session.execute(
                update(Task).where(Task.id == task_id)
                .values(status=TaskStatus.RUNNING, progress=0, message="准备上传 Xigua...")
            )
            await session.execute(
                update(Video).where(Video.id == video_id).values(status=VideoStatus.COMPLETED)
            )
            await session.commit()
        # Phase 4 不涉及上传


def _parse_srt(srt_content: str) -> list[dict]:
    """Parse SRT content into segments list (legacy support)."""
    import re
    segments = []
    pattern = re.compile(
        r'(\d+)\s*\n'
        r'(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*\n'
        r'((?:(?!\n\n|\r\n\r\n).)+)',
        re.DOTALL | re.MULTILINE,
    )
    for match in pattern.finditer(srt_content):
        start = _srt_time_to_seconds(match.group(2))
        end = _srt_time_to_seconds(match.group(3))
        text = match.group(4).strip().replace("\n", " ")
        text = re.sub(r'<[^>]+>', '', text)
        if text:
            segments.append({"start": start, "end": end, "text": text})
    return segments


def _srt_time_to_seconds(time_str: str) -> float:
    time_str = time_str.replace(",", ".")
    parts = time_str.split(":")
    h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
    return h * 3600 + m * 60 + s
