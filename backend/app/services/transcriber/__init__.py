"""
Transcription services package.

Provides transcription providers for speech-to-text conversion.
"""

from app.services.transcriber.base import (
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionSegment,
)

__all__ = [
    "TranscriptionProvider",
    "TranscriptionResult",
    "TranscriptionSegment",
]
