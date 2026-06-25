"""
Unit tests for TTS providers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os
import tempfile

from app.services.tts_new.base import TTSProvider, TTSResult


class TestTTSResult:
    """Tests for TTSResult dataclass."""

    def test_tts_result_creation(self):
        """Test TTSResult creation."""
        result = TTSResult(
            audio_data=b"audio data",
            duration=5.0,
            sample_rate=32000,
            format="mp3",
        )
        assert result.audio_data == b"audio data"
        assert result.duration == 5.0
        assert result.sample_rate == 32000
        assert result.format == "mp3"


class TestSiliconFlowTTSProvider:
    """Tests for SiliconFlowTTSProvider."""

    def test_provider_initialization(self):
        """Test SiliconFlowTTSProvider initialization."""
        from app.services.tts_new.siliconflow_provider import SiliconFlowTTSProvider

        provider = SiliconFlowTTSProvider(
            api_key="test-key",
            model="FunAudioLLM/CosyVoice2-0.5B",
            voice="alex",
            speed=1.0,
            gain=0,
        )
        assert provider.api_key == "test-key"
        assert provider.model == "FunAudioLLM/CosyVoice2-0.5B"
        assert provider.voice == "alex"
        assert provider.speed == 1.0
        assert provider.gain == 0

    def test_provider_is_loaded(self):
        """Test SiliconFlowTTSProvider is_loaded property."""
        from app.services.tts_new.siliconflow_provider import SiliconFlowTTSProvider

        provider = SiliconFlowTTSProvider()
        # API providers are always ready
        assert provider.is_loaded is True

    @pytest.mark.asyncio
    async def test_load_model(self):
        """Test load_model is no-op for API providers."""
        from app.services.tts_new.siliconflow_provider import SiliconFlowTTSProvider

        provider = SiliconFlowTTSProvider()
        await provider.load_model()  # Should not raise

    @pytest.mark.asyncio
    async def test_get_available_voices(self):
        """Test get_available_voices returns list."""
        from app.services.tts_new.siliconflow_provider import SiliconFlowTTSProvider

        provider = SiliconFlowTTSProvider()
        voices = await provider.get_available_voices()
        assert isinstance(voices, list)
        assert len(voices) > 0
        assert "id" in voices[0]
        assert "name" in voices[0]

    @pytest.mark.asyncio
    async def test_get_available_models(self):
        """Test get_available_models returns list."""
        from app.services.tts_new.siliconflow_provider import SiliconFlowTTSProvider

        provider = SiliconFlowTTSProvider()
        models = await provider.get_available_models()
        assert isinstance(models, list)
        assert len(models) > 0
        assert "id" in models[0]
        assert "name" in models[0]


class TestTTSService:
    """Tests for TTSService."""

    def test_service_initialization(self):
        """Test TTSService initialization."""
        from app.services.tts_new.service import TTSService
        from app.services.tts_new.siliconflow_provider import SiliconFlowTTSProvider

        service = TTSService()
        assert isinstance(service._provider, SiliconFlowTTSProvider)

    def test_service_custom_provider(self):
        """Test TTSService with custom provider."""
        from app.services.tts_new.service import TTSService

        mock_provider = MagicMock(spec=TTSProvider)
        service = TTSService(provider=mock_provider)
        assert service._provider is mock_provider
