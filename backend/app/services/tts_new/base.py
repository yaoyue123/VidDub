"""
TTS provider abstract base class.

Defines the interface for text-to-speech providers (edge-tts, SiliconFlow, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Optional


@dataclass
class TTSResult:
    """Result from a TTS operation."""
    audio_data: bytes
    format: str  # mp3, wav, opus, pcm
    sample_rate: int = 32000
    duration: Optional[float] = None


class TTSProvider(ABC):
    """Abstract base class for TTS providers.

    All TTS backends (edge-tts local, SiliconFlow API, etc.)
    must implement this interface.
    """

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: str = "default",
        speed: float = 1.0,
        gain: float = 0.0,
        format: str = "mp3",
        sample_rate: int = 32000,
    ) -> TTSResult:
        """Synthesize text to speech.

        Args:
            text: Text to synthesize.
            voice: Voice identifier (model:voice_name format for SiliconFlow).
            speed: Speech speed (0.25 to 4.0, default 1.0).
            gain: Volume gain in dB (-10 to 10, default 0).
            format: Output format (mp3, wav, opus, pcm).
            sample_rate: Output sample rate in Hz.

        Returns:
            TTSResult with audio data.

        Raises:
            RuntimeError: If synthesis fails.
        """
        pass

    @abstractmethod
    async def synthesize_stream(
        self,
        text: str,
        voice: str = "default",
        speed: float = 1.0,
        gain: float = 0.0,
        format: str = "mp3",
        sample_rate: int = 32000,
    ) -> AsyncGenerator[bytes, None]:
        """Synthesize text to speech with streaming response.

        Args:
            text: Text to synthesize.
            voice: Voice identifier.
            speed: Speech speed (0.25 to 4.0).
            gain: Volume gain in dB (-10 to 10).
            format: Output format.
            sample_rate: Output sample rate.

        Yields:
            Audio data chunks.
        """
        yield b""  # Placeholder for abstract method
        # This yield makes it a generator; subclasses should override properly

    @abstractmethod
    async def get_available_voices(self) -> list[dict[str, Any]]:
        """Get list of available voices.

        Returns:
            List of voice info dicts with keys: id, name, gender, language, style.
        """
        pass

    @abstractmethod
    async def get_available_models(self) -> list[dict[str, Any]]:
        """Get list of available TTS models.

        Returns:
            List of model info dicts with keys: id, name, description.
        """
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available (API key configured, etc.)."""
        pass
