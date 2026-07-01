"""
Edge-TTS Provider.

Implements text-to-speech using Microsoft Edge's free TTS engine (edge-tts).
No API key required — completely free, runs locally with low latency.

Supports 100+ voices across 50+ languages.
"""

import asyncio
import logging
import time
from typing import Any, AsyncIterator, Optional

from app.services.tts_new.base import TTSProvider, TTSResult

logger = logging.getLogger(__name__)

# Chinese voices available in edge-tts (the most relevant for our use case)
# Full list: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support
EDGE_VOICES = [
    {"id": "zh-CN-XiaoxiaoNeural", "name": "晓晓 (女声, 温柔)"},
    {"id": "zh-CN-XiaoyiNeural", "name": "晓伊 (女声, 亲切)"},
    {"id": "zh-CN-YunjianNeural", "name": "云健 (男声, 成熟)"},
    {"id": "zh-CN-YunxiNeural", "name": "云希 (男声, 阳光)"},
    {"id": "zh-CN-YunxiaNeural", "name": "云夏 (男声, 活力)"},
    {"id": "zh-CN-XiaochenNeural", "name": "晓辰 (女声, 知性)"},
    {"id": "zh-CN-XiaohanNeural", "name": "晓涵 (女声, 温暖)"},
    {"id": "zh-CN-XiaomengNeural", "name": "晓萌 (女声, 活泼)"},
    {"id": "zh-CN-XiaomoNeural", "name": "晓墨 (女声, 柔和)"},
    {"id": "zh-CN-XiaoqiuNeural", "name": "晓秋 (女声, 自然)"},
    {"id": "zh-CN-XiaoruiNeural", "name": "晓睿 (女声, 理智)"},
    {"id": "zh-CN-XiaoshuangNeural", "name": "晓双 (女声, 亲和)"},
    {"id": "zh-CN-YunyangNeural", "name": "云扬 (男声, 专业)"},
    {"id": "zh-CN-YunyeNeural", "name": "云野 (男声, 开朗)"},
    # English voices (for bilingual content)
    {"id": "en-US-JennyNeural", "name": "Jenny (美国, 女声)"},
    {"id": "en-US-GuyNeural", "name": "Guy (美国, 男声)"},
    {"id": "en-US-AriaNeural", "name": "Aria (美国, 女声)"},
    {"id": "en-GB-SoniaNeural", "name": "Sonia (英国, 女声)"},
    {"id": "en-GB-RyanNeural", "name": "Ryan (英国, 男声)"},
]


class EdgeTTSProvider(TTSProvider):
    """Edge-TTS provider using the edge-tts Python library.

    Completely free, no API key required. Runs locally with low latency.
    Supports neural voices with natural prosody.

    Note: First call may be slow as the module loads internally.
    Subsequent calls are fast (< 1s for short text).
    """

    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural", speed: float = 1.0, gain: int = 0):
        self._voice = voice
        self._speed = speed
        self._gain = gain
        self._available: Optional[bool] = None

    @property
    def is_loaded(self) -> bool:
        """Edge-TTS is always ready (no model to load)."""
        return True

    @property
    def is_available(self) -> bool:
        """Check if edge-tts module is importable."""
        if self._available is not None:
            return self._available
        try:
            import edge_tts  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False
        return self._available

    async def load_model(self) -> None:
        """No model to load for edge-tts."""
        pass

    @staticmethod
    def _speed_to_rate(speed: float) -> str:
        """Convert numeric speed to edge-tts rate string (+XX%).

        edge-tts rate format: +XX% (positive) or -XX% (negative).
        """
        if abs(speed - 1.0) < 0.01:
            return "+0%"
        percent = int((speed - 1.0) * 100)
        sign = "+" if percent >= 0 else ""
        return f"{sign}{percent}%"

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
        """Synthesize text to audio file using Edge-TTS.

        Args:
            text: Text to synthesize.
            output_path: Path to write audio file.
            voice: Voice ID (e.g., "zh-CN-XiaoxiaoNeural").
            model: (Unused by edge-tts)
            speed: Speech speed (0.25-4.0, default 1.0).
            gain: (Unused by edge-tts — volume is handled downstream)
            response_format: (Unused — edge-tts always outputs mp3)
            sample_rate: (Unused — edge-tts outputs 24kHz)

        Returns:
            TTSResult with timing and metadata.
        """
        import edge_tts

        if not text or not text.strip():
            raise ValueError("Text is empty")

        voice_id = voice or self._voice
        rate = self._speed_to_rate(speed or self._speed)

        start_time = time.time()

        try:
            communicate = edge_tts.Communicate(text, voice_id, rate=rate)
            await communicate.save(output_path)

            elapsed = time.time() - start_time

            # Estimate duration from file size
            import os
            file_size = os.path.getsize(output_path)
            # edge-tts outputs 24kHz MP3; rough estimate: ~8 KB/s
            estimated_duration = file_size / 8000 if file_size > 0 else 0

            logger.info(
                "Edge-TTS completed in %.1fs: %s (%d bytes, ~%.1fs audio, voice=%s, rate=%s)",
                elapsed, output_path, file_size, estimated_duration, voice_id, rate,
            )

            with open(output_path, "rb") as f:
                audio_data = f.read()

            return TTSResult(
                audio_data=audio_data,
                duration=estimated_duration,
                sample_rate=24000,
                format="mp3",
            )

        except Exception as e:
            logger.error("Edge-TTS failed: %s", e)
            raise RuntimeError(f"Edge-TTS synthesis failed: {e}") from e

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
        """Stream synthesized audio using Edge-TTS.

        Args:
            text: Text to synthesize.
            voice: Voice ID.
            model: (Unused)
            speed: Speech speed.
            gain: (Unused)
            response_format: (Unused)
            sample_rate: (Unused)

        Yields:
            Audio data chunks (MP3).
        """
        import edge_tts

        if not text or not text.strip():
            return

        voice_id = voice or self._voice
        rate = self._speed_to_rate(speed or self._speed)

        try:
            communicate = edge_tts.Communicate(text, voice_id, rate=rate)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]
        except Exception as e:
            logger.error("Edge-TTS stream failed: %s", e)
            raise RuntimeError(f"Edge-TTS stream failed: {e}") from e

    async def get_available_voices(self) -> list[dict[str, str]]:
        """Get list of available voices.

        Returns a curated list of common Chinese + English voices.
        The full list from Microsoft has 100+ voices; we return the
        most relevant subset for Chinese content production.

        Returns:
            List of voice dicts with 'id' and 'name' keys.
        """
        return EDGE_VOICES

    async def get_available_models(self) -> list[dict[str, str]]:
        """Get list of available models.

        Edge-TTS uses Microsoft's neural TTS engine — no model selection.

        Returns:
            List with a single entry representing the default engine.
        """
        return [{"id": "edge-tts", "name": "Microsoft Edge Neural TTS"}]
