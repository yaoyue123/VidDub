"""
Transcription provider abstract base class.

Defines the interface for speech-to-text providers (Whisper, SiliconFlow, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TranscriptionSegment:
    """A single transcription segment with timing information."""
    id: int
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    """Result from a transcription operation."""
    text: str
    segments: list[TranscriptionSegment] = field(default_factory=list)
    language: Optional[str] = None
    duration: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "text": self.text,
            "segments": [
                {
                    "id": seg.id,
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                }
                for seg in self.segments
            ],
            "language": self.language,
            "duration": self.duration,
        }


class TranscriptionProvider(ABC):
    """Abstract base class for transcription providers.

    All transcription backends (Whisper local, SiliconFlow API, etc.)
    must implement this interface.
    """

    @abstractmethod
    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        progress_callback: Optional[callable] = None,
    ) -> TranscriptionResult:
        """Transcribe an audio file.

        Args:
            audio_path: Path to the audio file (WAV, MP3, etc.).
            language: Language code (e.g., 'en', 'zh'). Auto-detected if None.
            progress_callback: Optional callback for progress updates.

        Returns:
            TranscriptionResult with text and segments.

        Raises:
            FileNotFoundError: If audio file not found.
            RuntimeError: If transcription fails.
        """
        pass

    @abstractmethod
    async def extract_audio(
        self,
        video_path: str,
        output_dir: Optional[str] = None,
    ) -> str:
        """Extract audio from video file.

        Args:
            video_path: Path to the video file.
            output_dir: Directory for output audio file.

        Returns:
            Path to extracted audio file.

        Raises:
            FileNotFoundError: If video file not found.
            RuntimeError: If extraction fails.
        """
        pass

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """Check if the provider is ready to transcribe."""
        pass

    @abstractmethod
    async def load_model(self) -> None:
        """Load/initialize the transcription model."""
        pass
