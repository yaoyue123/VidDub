"""
Whisper Transcription Provider.

Adapts the existing WhisperService to implement the TranscriptionProvider interface.
"""

from typing import Any, Callable, Optional

from app.services.transcriber.base import (
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionSegment,
)
from app.services.whisper_service import WhisperService


class WhisperProvider(TranscriptionProvider):
    """Whisper-based transcription provider.

    Wraps the existing WhisperService to implement the TranscriptionProvider interface.
    """

    def __init__(
        self,
        model_name: str = "small",
        device: str = "cpu",
        compute_type: str = "float32",
        download_root: Optional[str] = None,
    ):
        self._service = WhisperService(
            model_name=model_name,
            device=device,
            compute_type=compute_type,
            download_root=download_root,
        )

    @property
    def is_loaded(self) -> bool:
        """Check if the Whisper model is loaded."""
        return self._service.is_loaded

    async def load_model(self) -> None:
        """Load the Whisper model."""
        await self._service.load_model()

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
        """
        return await self._service.extract_audio(video_path, output_dir)

    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> TranscriptionResult:
        """Transcribe audio file using Whisper.

        Args:
            audio_path: Path to audio file (WAV/MP3).
            language: Language code (e.g., 'en', 'zh'). Auto-detected if None.
            progress_callback: Optional callback for progress updates.

        Returns:
            TranscriptionResult with text and segments.
        """
        result = await self._service.transcribe(
            audio_path=audio_path,
            language=language,
            progress_callback=progress_callback,
        )

        # Convert Whisper segments to TranscriptionSegment
        segments = []
        for seg in result.get("segments", []):
            segments.append(
                TranscriptionSegment(
                    id=seg.get("id", 0),
                    start=seg.get("start", 0.0),
                    end=seg.get("end", 0.0),
                    text=seg.get("text", "").strip(),
                )
            )

        return TranscriptionResult(
            text=result.get("text", ""),
            segments=segments,
            language=result.get("language"),
        )
