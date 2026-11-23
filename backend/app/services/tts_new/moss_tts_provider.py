"""MOSS-TTS-Nano local TTS provider.

Runs the OpenMOSS `MOSS-TTS-Nano` ONNX CPU pipeline in its own virtual
environment (its pinned torch/torchaudio versions must not leak into the
backend venv).  The upstream `infer_onnx.py` entrypoint supports built-in
voice presets, so no reference audio is required.

Setup (Windows):  backend/scripts/install_moss_tts.ps1
Manual setup:     see docs/CONFIGURATION.md → "MOSS-TTS-Nano (local)"
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import tempfile
from typing import AsyncIterator, Optional

from app.services.tts_new.base import TTSProvider, TTSResult

logger = logging.getLogger(__name__)

MOSS_BACKENDS = frozenset({"moss", "moss-nano", "moss-tts"})

MOSS_VOICES = [
    {"id": "Junhao", "name": "俊豪 · 中文男声（自然）"},
    {"id": "Zhiming", "name": "志明 · 中文男声（京味）"},
    {"id": "Weiguo", "name": "卫国 · 中文男声（说书）"},
    {"id": "Xiaoyu", "name": "小雨 · 中文女声（明亮）"},
    {"id": "Yuewen", "name": "月雯 · 中文女声（机车）"},
    {"id": "Lingyu", "name": "凌雨 · 中文女声（电台）"},
    {"id": "Trump", "name": "Trump · English male"},
    {"id": "Ava", "name": "Ava · English female"},
    {"id": "Bella", "name": "Bella · English female"},
    {"id": "Adam", "name": "Adam · English male"},
    {"id": "Nathan", "name": "Nathan · English male"},
]
MOSS_VOICE_IDS = frozenset(v["id"] for v in MOSS_VOICES)
DEFAULT_VOICE = "Junhao"

_REPO_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
DEFAULT_REPO_DIR = os.path.join(_REPO_ROOT, "data", "models", "MOSS-TTS-Nano")


def default_python_for(repo_dir: str) -> str:
    """Return the interpreter inside the MOSS repo's own venv."""
    if sys.platform == "win32":
        return os.path.join(repo_dir, ".venv", "Scripts", "python.exe")
    return os.path.join(repo_dir, ".venv", "bin", "python")


class MossTTSProvider(TTSProvider):
    """Local MOSS-TTS-Nano provider (0.1B, ONNX Runtime CPU)."""

    def __init__(
        self,
        repo_dir: Optional[str] = None,
        python_executable: Optional[str] = None,
        voice: str = DEFAULT_VOICE,
        cpu_threads: int = 4,
        timeout_sec: int = 1800,
    ) -> None:
        self._repo_dir = repo_dir
        self._python = python_executable
        self._voice = voice
        self._cpu_threads = cpu_threads
        self._timeout_sec = timeout_sec
        self._config_loaded = False

    @property
    def is_loaded(self) -> bool:
        return True

    @property
    def is_available(self) -> bool:
        repo = self._resolve_repo_dir()
        return bool(repo and os.path.exists(os.path.join(repo, "infer_onnx.py")))

    # ── config ──

    async def _load_config(self) -> None:
        """Read optional repo/python overrides from the DB config table."""
        if self._config_loaded:
            return
        self._config_loaded = True
        try:
            from sqlalchemy import select

            from app.core.database import async_session_factory
            from app.models.config import Config

            keys = ("moss_tts_repo_path", "moss_tts_python", "moss_tts_voice",
                    "moss_tts_cpu_threads")
            async with async_session_factory() as db:
                rows = (await db.execute(
                    select(Config).where(Config.key.in_(keys))
                )).scalars().all()
            values = {row.key: (row.value or "").strip() for row in rows}
        except Exception as exc:  # DB not initialised in unit tests
            logger.debug("MOSS TTS config lookup skipped: %s", exc)
            values = {}

        if not self._repo_dir and values.get("moss_tts_repo_path"):
            self._repo_dir = values["moss_tts_repo_path"]
        if not self._python and values.get("moss_tts_python"):
            self._python = values["moss_tts_python"]
        if values.get("moss_tts_voice"):
            self._voice = values["moss_tts_voice"]
        try:
            self._cpu_threads = int(values.get("moss_tts_cpu_threads") or self._cpu_threads)
        except ValueError:
            pass

    def _resolve_repo_dir(self) -> str:
        repo = self._repo_dir or os.environ.get("MOSS_TTS_REPO") or DEFAULT_REPO_DIR
        return os.path.abspath(os.path.expanduser(repo))

    def _resolve_python(self, repo: str) -> str:
        python = self._python or os.environ.get("MOSS_TTS_PYTHON")
        return os.path.abspath(os.path.expanduser(python)) if python else default_python_for(repo)

    # ── synthesis ──

    async def synthesize(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        speed: Optional[float] = None,
        gain: Optional[int] = None,
        response_format: Optional[str] = None,
        sample_rate: Optional[int] = None,
    ) -> TTSResult:
        if not text or not text.strip():
            raise ValueError("Text is empty")

        await self._load_config()
        repo = self._resolve_repo_dir()
        python = self._resolve_python(repo)

        if not os.path.exists(os.path.join(repo, "infer_onnx.py")):
            raise RuntimeError(
                f"MOSS-TTS-Nano not found at {repo}. Run "
                "backend/scripts/install_moss_tts.ps1 (see docs/CONFIGURATION.md)."
            )
        if not os.path.exists(python):
            raise RuntimeError(
                f"MOSS-TTS-Nano virtualenv python not found: {python}. "
                "Run backend/scripts/install_moss_tts.ps1."
            )

        voice_id = voice if voice in MOSS_VOICE_IDS else (self._voice or DEFAULT_VOICE)
        if voice_id not in MOSS_VOICE_IDS:
            voice_id = DEFAULT_VOICE

        fd, raw_wav = tempfile.mkstemp(prefix="viddub_moss_", suffix=".wav")
        os.close(fd)

        cmd = [
            python, "infer_onnx.py",
            "--disable-wetext-processing",
            "--voice", voice_id,
            "--text", text,
            "--output-audio-path", raw_wav,
            "--cpu-threads", str(self._cpu_threads),
        ]
        logger.info(
            "MOSS-TTS synthesizing %d chars (voice=%s, threads=%d)",
            len(text), voice_id, self._cpu_threads,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=repo,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self._timeout_sec,
                )
            except asyncio.TimeoutError:
                proc.kill()
                raise RuntimeError(
                    f"MOSS-TTS timed out after {self._timeout_sec}s"
                )

            if proc.returncode != 0 or not os.path.exists(raw_wav):
                tail = (stderr or b"").decode("utf-8", errors="replace")[-800:]
                raise RuntimeError(
                    f"MOSS-TTS failed (code={proc.returncode}): {tail}"
                )

            await self._post_process(raw_wav, output_path, speed)
            duration = await self._probe_duration(output_path)
            with open(output_path, "rb") as f:
                audio = f.read()
            return TTSResult(
                audio_data=audio,
                duration=duration,
                sample_rate=48000,
                format=os.path.splitext(output_path)[1].lstrip(".").lower() or "wav",
            )
        finally:
            if os.path.exists(raw_wav):
                try:
                    os.remove(raw_wav)
                except OSError:
                    pass

    async def _post_process(
        self, raw_wav: str, output_path: str, speed: Optional[float],
    ) -> None:
        """Apply speed changes and encode to the requested container."""
        from app.services.dubbing.ffmpeg import run_ffmpeg_async

        src = raw_wav
        if speed and abs(float(speed) - 1.0) > 0.01:
            from app.services.dubbing.alignment import compute_atempo_chain

            sped = raw_wav + ".speed.wav"
            await run_ffmpeg_async([
                "ffmpeg", "-y", "-i", raw_wav,
                "-af", compute_atempo_chain(float(speed)),
                "-ar", "48000", "-ac", "2", sped,
            ])
            src = sped
            raw_wav = sped

        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        if output_path.lower().endswith(".wav"):
            shutil.move(src, output_path)
        else:
            await run_ffmpeg_async([
                "ffmpeg", "-y", "-i", src,
                "-ar", "48000", "-ac", "2", output_path,
            ])
            try:
                os.remove(src)
            except OSError:
                pass

    @staticmethod
    async def _probe_duration(path: str) -> float:
        from app.services.dubbing.ffmpeg import ffprobe_duration

        try:
            return await ffprobe_duration(path)
        except Exception as exc:
            logger.warning("MOSS-TTS duration probe failed: %s", exc)
            return 0.0

    async def synthesize_stream(
        self,
        text: str,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        speed: Optional[float] = None,
        gain: Optional[int] = None,
        response_format: Optional[str] = None,
        sample_rate: Optional[int] = None,
    ) -> AsyncIterator[bytes]:
        fd, path = tempfile.mkstemp(prefix="viddub_moss_stream_", suffix=".wav")
        os.close(fd)
        try:
            result = await self.synthesize(
                text, path, voice=voice, model=model, speed=speed,
                gain=gain, response_format=response_format,
                sample_rate=sample_rate,
            )
            yield result.audio_data
        finally:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    # ── metadata ──

    async def get_available_voices(self) -> list[dict[str, str]]:
        return list(MOSS_VOICES)

    async def get_available_models(self) -> list[dict[str, str]]:
        return [{
            "id": "MOSS-TTS-Nano-100M",
            "name": "MOSS-TTS-Nano (local ONNX, 0.1B)",
        }]
