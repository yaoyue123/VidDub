"""
Integration tests for SiliconFlow API integration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import os

from app.services.transcriber.service import TranscriptionService
from app.services.tts_new.service import TTSService
from app.services.voice_cloner.service import VoiceClonerService


class TestTranscriptionServiceIntegration:
    """Integration tests for TranscriptionService."""

    @patch("app.services.transcriber.service._get_transcription_backend")
    @pytest.mark.asyncio
    async def test_transcription_service_whisper_integration(self, mock_get_backend):
        """Test TranscriptionService with Whisper backend."""
        mock_get_backend.return_value = "whisper"

        service = TranscriptionService()
        provider = await service._get_provider()

        # Verify provider type
        from app.services.transcriber.whisper_provider import WhisperProvider

        assert isinstance(provider, WhisperProvider)

    @patch("app.services.transcriber.service._get_transcription_backend")
    @patch("app.services.transcriber.service._get_transcription_model")
    @pytest.mark.asyncio
    async def test_transcription_service_siliconflow_integration(
        self, mock_get_model, mock_get_backend
    ):
        """Test TranscriptionService with SiliconFlow backend."""
        mock_get_backend.return_value = "siliconflow"
        mock_get_model.return_value = "FunAudioLLM/SenseVoiceSmall"

        service = TranscriptionService()
        provider = await service._get_provider()

        # Verify provider type
        from app.services.transcriber.siliconflow_provider import (
            SiliconFlowTranscriptionProvider,
        )

        assert isinstance(provider, SiliconFlowTranscriptionProvider)


class TestTTSServiceIntegration:
    """Integration tests for TTSService."""

    def test_tts_service_provider_integration(self):
        """Test TTSService with SiliconFlow provider."""
        service = TTSService()

        # Verify provider type
        from app.services.tts_new.siliconflow_provider import SiliconFlowTTSProvider

        assert isinstance(service._provider, SiliconFlowTTSProvider)

    @pytest.mark.asyncio
    async def test_tts_service_voices_integration(self):
        """Test TTSService get_available_voices."""
        service = TTSService()
        voices = await service.get_available_voices()

        # Verify voices are returned
        assert isinstance(voices, list)
        assert len(voices) > 0

        # Verify voice structure
        for voice in voices:
            assert "id" in voice
            assert "name" in voice

    @pytest.mark.asyncio
    async def test_tts_service_models_integration(self):
        """Test TTSService get_available_models."""
        service = TTSService()
        models = await service.get_available_models()

        # Verify models are returned
        assert isinstance(models, list)
        assert len(models) > 0

        # Verify model structure
        for model in models:
            assert "id" in model
            assert "name" in model


class TestVoiceClonerServiceIntegration:
    """Integration tests for VoiceClonerService."""

    def test_voice_cloner_service_provider_integration(self):
        """Test VoiceClonerService with SiliconFlow provider."""
        service = VoiceClonerService()

        # Verify provider type
        from app.services.voice_cloner.siliconflow_provider import (
            SiliconFlowVoiceCloner,
        )

        assert isinstance(service._provider, SiliconFlowVoiceCloner)

    @pytest.mark.asyncio
    async def test_voice_cloner_service_list_integration(self):
        """Test VoiceClonerService list_voices."""
        service = VoiceClonerService()
        voices = await service.list_voices()

        # Verify voices are returned
        assert isinstance(voices, list)

    @pytest.mark.asyncio
    async def test_voice_cloner_service_get_integration(self):
        """Test VoiceClonerService get_voice."""
        service = VoiceClonerService()

        # Add a test voice
        service._provider._temp_uris["test"] = "speech:test:model:123"

        # Get the voice
        voice = await service.get_voice("test")

        # Verify voice is returned
        assert voice is not None
        assert voice["name"] == "test"
        assert voice["uri"] == "speech:test:model:123"


class TestConfigSeederIntegration:
    """Integration tests for config seeder."""

    def test_config_seeder_has_new_configs(self):
        """Test config_seeder has new SiliconFlow config items."""
        from app.services.config_seeder import DEFAULT_CONFIGS

        # Verify new config items exist
        assert "transcription_backend" in DEFAULT_CONFIGS
        assert "transcription_model" in DEFAULT_CONFIGS
        assert "tts_model" in DEFAULT_CONFIGS
        assert "tts_voice" in DEFAULT_CONFIGS
        assert "tts_speed" in DEFAULT_CONFIGS
        assert "tts_gain" in DEFAULT_CONFIGS
        assert "tts_format" in DEFAULT_CONFIGS
        assert "tts_sample_rate" in DEFAULT_CONFIGS

    def test_config_seeder_values(self):
        """Test config_seeder has correct default values."""
        from app.services.config_seeder import DEFAULT_CONFIGS

        assert DEFAULT_CONFIGS["transcription_backend"]["value"] == "whisper"
        assert DEFAULT_CONFIGS["tts_model"]["value"] == "FunAudioLLM/CosyVoice2-0.5B"
        assert DEFAULT_CONFIGS["tts_format"]["value"] == "mp3"
