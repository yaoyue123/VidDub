"""
Unit tests for transcription providers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os
import tempfile

from app.services.transcriber.base import (
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionSegment,
)


class TestTranscriptionResult:
    """Tests for TranscriptionResult dataclass."""

    def test_transcription_result_creation(self):
        """Test TranscriptionResult creation with required fields."""
        result = TranscriptionResult(text="Hello world")
        assert result.text == "Hello world"
        assert result.segments == []
        assert result.language is None

    def test_transcription_result_with_segments(self):
        """Test TranscriptionResult with segments."""
        segments = [
            TranscriptionSegment(id=0, start=0.0, end=1.0, text="Hello"),
            TranscriptionSegment(id=1, start=1.0, end=2.0, text="world"),
        ]
        result = TranscriptionResult(
            text="Hello world",
            segments=segments,
            language="en",
        )
        assert result.text == "Hello world"
        assert len(result.segments) == 2
        assert result.language == "en"

    def test_transcription_segment_creation(self):
        """Test TranscriptionSegment creation."""
        segment = TranscriptionSegment(id=0, start=0.0, end=1.0, text="Hello")
        assert segment.id == 0
        assert segment.start == 0.0
        assert segment.end == 1.0
        assert segment.text == "Hello"


class TestWhisperProvider:
    """Tests for WhisperProvider."""

    @patch("app.services.transcriber.whisper_provider.WhisperService")
    def test_whisper_provider_initialization(self, mock_whisper_service):
        """Test WhisperProvider initialization."""
        from app.services.transcriber.whisper_provider import WhisperProvider

        provider = WhisperProvider(model_name="small", device="cpu")
        mock_whisper_service.assert_called_once_with(
            model_name="small",
            device="cpu",
            compute_type="float32",
            download_root=None,
        )

    @patch("app.services.transcriber.whisper_provider.WhisperService")
    def test_whisper_provider_is_loaded(self, mock_whisper_service):
        """Test WhisperProvider is_loaded property."""
        from app.services.transcriber.whisper_provider import WhisperProvider

        mock_instance = MagicMock()
        mock_instance.is_loaded = True
        mock_whisper_service.return_value = mock_instance

        provider = WhisperProvider()
        assert provider.is_loaded is True


class TestSiliconFlowTranscriptionProvider:
    """Tests for SiliconFlowTranscriptionProvider."""

    def test_provider_initialization(self):
        """Test SiliconFlowTranscriptionProvider initialization."""
        from app.services.transcriber.siliconflow_provider import (
            SiliconFlowTranscriptionProvider,
        )

        provider = SiliconFlowTranscriptionProvider(
            api_key="test-key",
            model="FunAudioLLM/SenseVoiceSmall",
        )
        assert provider.api_key == "test-key"
        assert provider.model == "FunAudioLLM/SenseVoiceSmall"

    def test_provider_is_loaded(self):
        """Test SiliconFlowTranscriptionProvider is_loaded property."""
        from app.services.transcriber.siliconflow_provider import (
            SiliconFlowTranscriptionProvider,
        )

        provider = SiliconFlowTranscriptionProvider()
        # API providers are always ready
        assert provider.is_loaded is False  # Before load_model
        provider._loaded = True
        assert provider.is_loaded is True

    @pytest.mark.asyncio
    async def test_load_model(self):
        """Test load_model sets loaded state."""
        from app.services.transcriber.siliconflow_provider import (
            SiliconFlowTranscriptionProvider,
        )

        provider = SiliconFlowTranscriptionProvider()
        await provider.load_model()
        assert provider.is_loaded is True

    @pytest.mark.asyncio
    async def test_transcribe_file_not_found(self):
        """Test transcribe raises FileNotFoundError for missing file."""
        from app.services.transcriber.siliconflow_provider import (
            SiliconFlowTranscriptionProvider,
        )

        provider = SiliconFlowTranscriptionProvider(api_key="test-key")
        with pytest.raises(FileNotFoundError):
            await provider.transcribe("/nonexistent/audio.wav")

    @pytest.mark.asyncio
    async def test_extract_audio_file_not_found(self):
        """Test extract_audio raises FileNotFoundError for missing file."""
        from app.services.transcriber.siliconflow_provider import (
            SiliconFlowTranscriptionProvider,
        )

        provider = SiliconFlowTranscriptionProvider()
        with pytest.raises(FileNotFoundError):
            await provider.extract_audio("/nonexistent/video.mp4")


class TestTranscriptionService:
    """Tests for TranscriptionService."""

    @patch("app.services.transcriber.service._get_transcription_backend")
    @pytest.mark.asyncio
    async def test_get_provider_whisper(self, mock_get_backend):
        """Test TranscriptionService selects Whisper provider."""
        from app.services.transcriber.service import TranscriptionService

        mock_get_backend.return_value = "whisper"
        service = TranscriptionService()
        provider = await service._get_provider()
        from app.services.transcriber.whisper_provider import WhisperProvider

        assert isinstance(provider, WhisperProvider)

    @patch("app.services.transcriber.service._get_transcription_backend")
    @patch("app.services.transcriber.service._get_transcription_model")
    @pytest.mark.asyncio
    async def test_get_provider_siliconflow(self, mock_get_model, mock_get_backend):
        """Test TranscriptionService selects SiliconFlow provider."""
        from app.services.transcriber.service import TranscriptionService

        mock_get_backend.return_value = "siliconflow"
        mock_get_model.return_value = "FunAudioLLM/SenseVoiceSmall"
        service = TranscriptionService()
        provider = await service._get_provider()
        from app.services.transcriber.siliconflow_provider import (
            SiliconFlowTranscriptionProvider,
        )

        assert isinstance(provider, SiliconFlowTranscriptionProvider)
