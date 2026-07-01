"""
TTS Service (new).

High-level text-to-speech service with config-based provider selection.
Supports SiliconFlow API and Edge-TTS (free, local).
"""

import logging
from typing import AsyncIterator, Optional

from app.core.database import async_session_factory
from app.models.config import Config
from app.services.tts_new.base import TTSProvider, TTSResult
from app.services.tts_new.siliconflow_provider import SiliconFlowTTSProvider

logger = logging.getLogger(__name__)


async def _get_tts_backend() -> str:
    """Read TTS backend from DB config."""
    try:
        async with async_session_factory() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(Config).where(Config.key == "tts_backend")
            )
            config = result.scalar_one_or_none()
        return config.value if config else "siliconflow"
    except Exception:
        return "siliconflow"


class TTSService:
    """High-level TTS service with config-based provider selection.

    Automatically selects SiliconFlow or Edge-TTS based on configuration.
    """

    def __init__(self, provider: Optional[TTSProvider] = None):
        self._provider = provider
        self._backend: Optional[str] = None

    async def _get_provider(self) -> TTSProvider:
        """Get or create the appropriate provider based on config."""
        backend = await _get_tts_backend()

        if self._backend != backend or self._provider is None:
            self._backend = backend

            if backend == "edge-tts":
                from app.services.tts_new.edge_tts_provider import EdgeTTSProvider
                self._provider = EdgeTTSProvider()
                logger.info("Using Edge-TTS provider (free, local)")
            else:
                self._provider = SiliconFlowTTSProvider()
                logger.info("Using SiliconFlow TTS provider")

        return self._provider

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
        """Synthesize text to audio file.

        Args:
            text: Text to synthesize.
            output_path: Path to write audio file.
            voice: Voice ID.
            model: Model ID.
            speed: Speech speed (0.25-4.0).
            gain: Volume gain dB (-10 to 10).
            response_format: Output format (mp3/wav/opus/pcm).
            sample_rate: Sample rate in Hz.

        Returns:
            TTSResult with timing and metadata.
        """
        provider = await self._get_provider()
        return await provider.synthesize(
            text=text,
            output_path=output_path,
            voice=voice,
            model=model,
            speed=speed,
            gain=gain,
            response_format=response_format,
            sample_rate=sample_rate,
        )

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
        """Stream synthesized audio.

        Args:
            text: Text to synthesize.
            voice: Voice ID.
            model: Model ID.
            speed: Speech speed.
            gain: Volume gain dB.
            response_format: Output format.
            sample_rate: Sample rate.

        Yields:
            Audio data chunks.
        """
        provider = await self._get_provider()
        async for chunk in provider.synthesize_stream(
            text=text,
            voice=voice,
            model=model,
            speed=speed,
            gain=gain,
            response_format=response_format,
            sample_rate=sample_rate,
        ):
            yield chunk

    async def get_available_voices(self) -> list[dict[str, str]]:
        """Get list of available voices.

        Returns:
            List of voice dicts with 'id' and 'name' keys.
        """
        provider = await self._get_provider()
        return await provider.get_available_voices()

    async def get_available_models(self) -> list[dict[str, str]]:
        """Get list of available TTS models.

        Returns:
            List of model dicts with 'id' and 'name' keys.
        """
        provider = await self._get_provider()
        return await provider.get_available_models()
