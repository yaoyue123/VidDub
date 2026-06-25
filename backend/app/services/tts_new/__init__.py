"""
TTS services package (new adapter pattern).

Provides TTS providers for text-to-speech conversion.
"""

from app.services.tts_new.base import TTSProvider, TTSResult

__all__ = [
    "TTSProvider",
    "TTSResult",
]
