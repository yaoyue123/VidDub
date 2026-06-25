"""
TTS Service (new).

High-level text-to-speech service using SiliconFlow API.
"""

import logging
from typing import AsyncIterator, Optional

from app.services.tts_new.base import TTSProvider, TTSResult
from app.services.tts_new.siliconflow_provider import SiliconFlowTTSProvider

logger = logging.getLogger(__name__)


class TTSService:
    """High-level TTS service.

    Provides a unified interface for text-to-speech operations using SiliconFlow.
    """

    def __init__(self, provider: Optional[TTSProvider] = None):
        self._provider = provider or SiliconFlowTTSProvider()

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
        return await self._provider.synthesize(
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
        async for chunk in self._provider.synthesize_stream(
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
        return await self._provider.get_available_voices()

    async def get_available_models(self) -> list[dict[str, str]]:
        """Get list of available TTS models.

        Returns:
            List of model dicts with 'id' and 'name' keys.
        """
        return await self._provider.get_available_models()
