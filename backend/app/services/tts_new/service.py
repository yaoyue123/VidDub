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
            elif backend in ("moss", "moss-nano", "moss-tts"):
                from app.services.tts_new.moss_tts_provider import MossTTSProvider
                self._provider = MossTTSProvider()
                logger.info("Using MOSS-TTS-Nano provider (local ONNX)")
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
        voice = self._normalize_voice(voice)
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

    def _normalize_voice(self, voice: Optional[str]) -> Optional[str]:
        """Drop voices that belong to a different TTS backend.

        ``tts_voice_simple`` defaults to the SiliconFlow name ``anna``; after
        switching ``tts_backend`` to ``edge-tts`` that value is not a valid
        Edge voice and the API rejects it.  Symmetrically, an Edge voice must
        not be sent to SiliconFlow.  Falling back to the provider default keeps
        the pipeline working when users switch backends in the Settings UI.
        """
        if not voice:
            return voice

        from app.services.tts_new.moss_tts_provider import MOSS_BACKENDS, MOSS_VOICE_IDS

        if self._backend in MOSS_BACKENDS:
            if voice in MOSS_VOICE_IDS:
                return voice
            logger.warning(
                "Voice %r is not a MOSS-TTS preset; using %s",
                voice, "Junhao",
            )
            return None

        is_edge_voice = voice.endswith("Neural") and "-" in voice
        if self._backend == "edge-tts" and not is_edge_voice:
            logger.warning(
                "Voice %r is not an Edge-TTS voice; using provider default", voice,
            )
            return None
        if self._backend != "edge-tts" and is_edge_voice:
            logger.warning(
                "Edge-TTS voice %r cannot be used with backend %r; "
                "using provider default", voice, self._backend,
            )
            return None
        return voice

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
        voice = self._normalize_voice(voice)
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
