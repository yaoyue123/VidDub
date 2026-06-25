"""
SiliconFlow TTS Provider.

Implements text-to-speech using SiliconFlow Audio Speech API.
"""

import asyncio
import logging
import time
from typing import Any, AsyncIterator, Optional

import httpx

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.config import Config
from app.services.tts_new.base import TTSProvider, TTSResult

logger = logging.getLogger(__name__)

DEFAULT_MODEL = settings.siliconflow_tts_model

# Available voices (from SiliconFlow docs)
# Male: alex, benjamin, charles, david
# Female: anna, bella, claire, diana
AVAILABLE_VOICES = [
    {"id": "alex", "name": "Alex (沉稳男声)"},
    {"id": "benjamin", "name": "Benjamin (低沉男声)"},
    {"id": "charles", "name": "Charles (磁性男声)"},
    {"id": "david", "name": "David (欢快男声)"},
    {"id": "anna", "name": "Anna (沉稳女声)"},
    {"id": "bella", "name": "Bella (激情女声)"},
    {"id": "claire", "name": "Claire (温柔女声)"},
    {"id": "diana", "name": "Diana (欢快女声)"},
]

# Available models
AVAILABLE_MODELS = [
    {"id": "FunAudioLLM/CosyVoice2-0.5B", "name": "CosyVoice2"},
    {"id": "fnlp/MOSS-TTSD-v0.5", "name": "MOSS-TTS"},
]


def _get_api_key_sync() -> str:
    """Read API key from unified settings (single source of truth)."""
    return settings.siliconflow_api_key.strip()


async def _get_tts_config() -> dict[str, str]:
    """Read TTS config from DB."""
    async with async_session_factory() as db:
        from sqlalchemy import select
        result = await db.execute(select(Config))
        configs = {c.key: c.value for c in result.scalars().all()}

    return {
        "model": configs.get("tts_model", DEFAULT_MODEL),
        "voice": configs.get("tts_voice", f"{DEFAULT_MODEL}:alex"),
        "speed": configs.get("tts_speed", "1.0"),
        "gain": configs.get("tts_gain", "0"),
        "format": configs.get("tts_format", "mp3"),
        "sample_rate": configs.get("tts_sample_rate", "32000"),
    }


class SiliconFlowTTSProvider(TTSProvider):
    """SiliconFlow TTS provider using Audio Speech API.

    Supports CosyVoice2 and MOSS-TTS models for text-to-speech.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        voice: str = "alex",
        speed: float = 1.0,
        gain: int = 0,
    ):
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.speed = speed
        self.gain = gain

    @property
    def is_loaded(self) -> bool:
        """Always ready for API-based TTS."""
        return True

    @property
    def is_available(self) -> bool:
        """Check if provider is available (API key configured)."""
        return self.api_key is not None

    async def load_model(self) -> None:
        """No local model to load for API-based TTS."""
        pass

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

    async def _get_voice_config(self, voice: Optional[str] = None) -> str:
        """Get voice ID, handling URI format for cloned voices."""
        if voice:
            return voice
        return self.voice

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
            voice: Voice ID (e.g., "alex" or "speech:name:model:id").
            model: Model ID.
            speed: Speech speed (0.25-4.0).
            gain: Volume gain dB (-10 to 10).
            response_format: Output format (mp3/wav/opus/pcm).
            sample_rate: Sample rate in Hz.

        Returns:
            TTSResult with timing and metadata.
        """
        api_key = await self._ensure_api_key()

        # Get defaults from config
        config = await _get_tts_config()

        model = model or self.model
        voice = await self._get_voice_config(voice)
        # Qualify voice with model prefix (required by SiliconFlow API)
        if ":" not in voice:
            voice = f"{model}:{voice}"
        speed = speed or self.speed
        gain = gain or self.gain
        response_format = response_format or config["format"]
        sample_rate = int(sample_rate or config["sample_rate"])

        start_time = time.time()

        headers = {"Authorization": f"Bearer {api_key}"}

        payload = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": response_format,
            "sample_rate": sample_rate,
            "speed": speed,
            "gain": gain,
        }

        speech_url = f"{settings.siliconflow_base_url.rstrip('/')}/audio/speech"
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    speech_url,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()

                # Write audio data
                with open(output_path, "wb") as f:
                    f.write(response.content)

                elapsed = time.time() - start_time

                # Estimate duration (rough: ~16 bytes per sample at 16kHz)
                audio_size = len(response.content)
                estimated_duration = audio_size / (sample_rate * 2)  # 16-bit audio

                logger.info(
                    "TTS completed in %.1fs: %d bytes, ~%.1fs audio",
                    elapsed,
                    audio_size,
                    estimated_duration,
                )

                return TTSResult(
                    audio_path=output_path,
                    duration=estimated_duration,
                    sample_rate=sample_rate,
                    format=response_format,
                )

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning("Rate limited, retrying after delay...")
                    await asyncio.sleep(5)
                    return await self.synthesize(
                        text, output_path, voice, model,
                        speed, gain, response_format, sample_rate
                    )
                raise RuntimeError(
                    f"TTS failed: {e.response.status_code} {e.response.text}"
                )
            except Exception as e:
                raise RuntimeError(f"TTS failed: {e}")

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
        api_key = await self._ensure_api_key()

        config = await _get_tts_config()

        model = model or self.model
        voice = await self._get_voice_config(voice)
        # Qualify voice with model prefix (required by SiliconFlow API)
        if ":" not in voice:
            voice = f"{model}:{voice}"
        speed = speed or self.speed
        gain = gain or self.gain
        response_format = response_format or config["format"]
        sample_rate = int(sample_rate or config["sample_rate"])

        headers = {"Authorization": f"Bearer {api_key}"}

        payload = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": response_format,
            "sample_rate": sample_rate,
            "speed": speed,
            "gain": gain,
        }

        speech_url = f"{settings.siliconflow_base_url.rstrip('/')}/audio/speech"
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                async with client.stream(
                    "POST",
                    speech_url,
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        yield chunk

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning("Rate limited, retrying after delay...")
                    await asyncio.sleep(5)
                    async for chunk in self.synthesize_stream(
                        text, voice, model, speed, gain,
                        response_format, sample_rate
                    ):
                        yield chunk
                else:
                    raise RuntimeError(
                        f"TTS stream failed: {e.response.status_code} "
                        f"{e.response.text}"
                    )
            except Exception as e:
                raise RuntimeError(f"TTS stream failed: {e}")

    async def get_available_voices(self) -> list[dict[str, str]]:
        """Get list of available voices.

        Returns:
            List of voice dicts with 'id' and 'name' keys.
        """
        return AVAILABLE_VOICES

    async def get_available_models(self) -> list[dict[str, str]]:
        """Get list of available TTS models.

        Returns:
            List of model dicts with 'id' and 'name' keys.
        """
        return AVAILABLE_MODELS
