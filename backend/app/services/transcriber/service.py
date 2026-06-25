"""
Transcription Service.

High-level service that provides config-based provider selection.
"""

import logging
from typing import Any, Callable, Optional

from app.core.database import async_session_factory
from app.models.config import Config
from app.services.transcriber.base import TranscriptionProvider, TranscriptionResult
from app.services.transcriber.whisper_provider import WhisperProvider
from app.services.transcriber.siliconflow_provider import SiliconFlowTranscriptionProvider

logger = logging.getLogger(__name__)


async def _get_transcription_backend() -> str:
    """Read transcription backend from DB config."""
    async with async_session_factory() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(Config).where(Config.key == "transcription_backend")
        )
        config = result.scalar_one_or_none()
    return config.value if config else "whisper"


async def _get_transcription_model() -> str:
    """Read transcription model from DB config."""
    async with async_session_factory() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(Config).where(Config.key == "transcription_model")
        )
        config = result.scalar_one_or_none()
    return config.value if config else "FunAudioLLM/SenseVoiceSmall"


class TranscriptionService:
    """High-level transcription service with config-based provider selection.

    Automatically selects Whisper or SiliconFlow based on configuration.
    """

    def __init__(self):
        self._provider: Optional[TranscriptionProvider] = None
        self._backend: Optional[str] = None

    async def _get_provider(self) -> TranscriptionProvider:
        """Get or create the appropriate provider based on config."""
        backend = await _get_transcription_backend()

        # Recreate provider if backend changed
        if self._backend != backend or self._provider is None:
            self._backend = backend

            if backend == "siliconflow":
                model = await _get_transcription_model()
                self._provider = SiliconFlowTranscriptionProvider(model=model)
                logger.info("Using SiliconFlow transcription provider")
            else:
                self._provider = WhisperProvider()
                logger.info("Using Whisper transcription provider")

        return self._provider

    @property
    def is_loaded(self) -> bool:
        """Check if the provider is loaded."""
        return self._provider is not None and self._provider.is_loaded

    async def load_model(self) -> None:
        """Load the provider model."""
        provider = await self._get_provider()
        await provider.load_model()

    async def extract_audio(
        self,
        video_path: str,
        output_dir: Optional[str] = None,
    ) -> str:
        """Extract audio from video.

        Args:
            video_path: Path to the video file.
            output_dir: Directory for output audio file.

        Returns:
            Path to extracted audio file.
        """
        provider = await self._get_provider()
        return await provider.extract_audio(video_path, output_dir)

    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> TranscriptionResult:
        """Transcribe audio file.

        Args:
            audio_path: Path to audio file (WAV/MP3).
            language: Language code (e.g., 'en', 'zh'). Auto-detected if None.
            progress_callback: Optional callback for progress updates.

        Returns:
            TranscriptionResult with text and segments.
        """
        provider = await self._get_provider()
        return await provider.transcribe(audio_path, language, progress_callback)
