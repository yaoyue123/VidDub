"""
SiliconFlow Transcription Provider.

Implements speech-to-text using SiliconFlow Audio Transcriptions API.
"""

import asyncio
import logging
import os
import time
from typing import Any, Callable, Optional

import httpx

from app.core.config import settings
from app.services.transcriber.base import (
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionSegment,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = settings.siliconflow_stt_model


def _get_api_key_sync() -> str:
    """Read API key from unified settings (single source of truth)."""
    return settings.siliconflow_api_key.strip()


class SiliconFlowTranscriptionProvider(TranscriptionProvider):
    """SiliconFlow transcription provider using Audio Transcriptions API.

    Supports SenseVoice and TeleSpeechASR models for speech-to-text.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        """Always ready for API-based transcription."""
        return self._loaded

    async def load_model(self) -> None:
        """No local model to load for API-based transcription."""
        self._loaded = True

    async def _ensure_api_key(self) -> str:
        """Ensure API key is available."""
        if self.api_key:
            return self.api_key
        key = _get_api_key_sync()
        if not key:
            raise RuntimeError(
                "SiliconFlow API key not configured. "
                "Set SILICONFLOW_API_KEY in backend/.env"
            )
        return key

    async def extract_audio(
        self,
        video_path: str,
        output_dir: Optional[str] = None,
    ) -> str:
        """Extract audio from video using ffmpeg.

        Args:
            video_path: Path to the video file.
            output_dir: Directory for output audio file.

        Returns:
            Path to extracted audio file.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if output_dir is None:
            output_dir = os.path.dirname(video_path)

        # Generate output filename
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        audio_path = os.path.join(output_dir, f"{base_name}.wav")

        # Use ffmpeg to extract audio
        cmd = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            audio_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(
                f"FFmpeg failed with code {process.returncode}: "
                f"{stderr.decode()}"
            )

        return audio_path

    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> TranscriptionResult:
        """Transcribe audio file using SiliconFlow API.

        Args:
            audio_path: Path to audio file (WAV/MP3).
            language: Language code (optional).
            progress_callback: Not used for API transcription.

        Returns:
            TranscriptionResult with text and segments.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        api_key = await self._ensure_api_key()

        # Report progress
        if progress_callback:
            progress_callback({
                "step": "transcribing",
                "progress": 0,
                "message": "Starting transcription...",
            })

        start_time = time.time()

        with open(audio_path, "rb") as f:
            audio_data = f.read()

        # Determine MIME type
        ext = os.path.splitext(audio_path)[1].lower()
        mime_map = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".opus": "audio/opus",
            ".pcm": "audio/pcm",
        }
        mime_type = mime_map.get(ext, "audio/mpeg")
        filename = os.path.basename(audio_path)

        headers = {"Authorization": f"Bearer {api_key}"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {
                "file": (filename, audio_data, mime_type),
            }
            data = {
                "model": self.model,
            }
            if language:
                data["language"] = language

            try:
                transcriptions_url = f"{settings.siliconflow_base_url.rstrip('/')}/audio/transcriptions"
                response = await client.post(
                    transcriptions_url,
                    files=files,
                    data=data,
                )
                response.raise_for_status()
                result = response.json()

                elapsed = time.time() - start_time
                text = result.get("text", "")

                if progress_callback:
                    progress_callback({
                        "step": "transcribing",
                        "progress": 100,
                        "message": f"Transcription completed in {elapsed:.1f}s",
                    })

                logger.info(
                    "Transcription completed in %.1fs: %d chars",
                    elapsed,
                    len(text),
                )

                # SiliconFlow returns full text, no segments
                return TranscriptionResult(
                    text=text,
                    segments=[],  # API doesn't return segments
                    language=result.get("language", language),
                )

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning("Rate limited, retrying after delay...")
                    await asyncio.sleep(5)
                    return await self.transcribe(
                        audio_path, language, progress_callback
                    )
                raise RuntimeError(
                    f"Transcription failed: {e.response.status_code} "
                    f"{e.response.text}"
                )
            except Exception as e:
                raise RuntimeError(f"Transcription failed: {e}")
