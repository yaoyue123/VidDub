"""
Unit tests for voice cloner.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os
import tempfile

from app.services.voice_cloner.siliconflow_provider import SiliconFlowVoiceCloner
from app.services.voice_cloner.service import VoiceClonerService


class TestSiliconFlowVoiceCloner:
    """Tests for SiliconFlowVoiceCloner."""

    def test_provider_initialization(self):
        """Test SiliconFlowVoiceCloner initialization."""
        provider = SiliconFlowVoiceCloner(
            api_key="test-key",
            model="FunAudioLLM/CosyVoice2-0.5B",
        )
        assert provider.api_key == "test-key"
        assert provider.model == "FunAudioLLM/CosyVoice2-0.5B"

    def test_provider_default_initialization(self):
        """Test SiliconFlowVoiceCloner default initialization."""
        provider = SiliconFlowVoiceCloner()
        assert provider.api_key is None
        assert provider.model == "FunAudioLLM/CosyVoice2-0.5B"

    @pytest.mark.asyncio
    async def test_upload_voice_file_not_found(self):
        """Test upload_voice raises FileNotFoundError for missing file."""
        provider = SiliconFlowVoiceCloner(api_key="test-key")
        with pytest.raises(FileNotFoundError):
            await provider.upload_voice("/nonexistent/audio.mp3", "test", "hello")

    @pytest.mark.asyncio
    async def test_get_uri(self):
        """Test get_uri returns stored URI."""
        provider = SiliconFlowVoiceCloner()
        provider._temp_uris["test"] = "speech:test:model:123"
        uri = await provider.get_uri("test")
        assert uri == "speech:test:model:123"

    @pytest.mark.asyncio
    async def test_get_uri_not_found(self):
        """Test get_uri returns None for missing voice."""
        provider = SiliconFlowVoiceCloner()
        uri = await provider.get_uri("nonexistent")
        assert uri is None

    @pytest.mark.asyncio
    async def test_list_voices(self):
        """Test list_voices returns stored voices."""
        provider = SiliconFlowVoiceCloner()
        provider._temp_uris["voice1"] = "speech:voice1:model:1"
        provider._temp_uris["voice2"] = "speech:voice2:model:2"
        voices = await provider.list_voices()
        assert len(voices) == 2
        assert {"name": "voice1", "uri": "speech:voice1:model:1"} in voices
        assert {"name": "voice2", "uri": "speech:voice2:model:2"} in voices

    @pytest.mark.asyncio
    async def test_delete_voice(self):
        """Test delete_voice removes stored voice."""
        provider = SiliconFlowVoiceCloner()
        provider._temp_uris["test"] = "speech:test:model:123"
        result = await provider.delete_voice("test")
        assert result is True
        assert "test" not in provider._temp_uris

    @pytest.mark.asyncio
    async def test_delete_voice_not_found(self):
        """Test delete_voice returns False for missing voice."""
        provider = SiliconFlowVoiceCloner()
        result = await provider.delete_voice("nonexistent")
        assert result is False


class TestVoiceClonerService:
    """Tests for VoiceClonerService."""

    def test_service_initialization(self):
        """Test VoiceClonerService initialization."""
        service = VoiceClonerService()
        assert isinstance(service._provider, SiliconFlowVoiceCloner)

    def test_service_custom_provider(self):
        """Test VoiceClonerService with custom provider."""
        mock_provider = MagicMock(spec=SiliconFlowVoiceCloner)
        service = VoiceClonerService(provider=mock_provider)
        assert service._provider is mock_provider

    @pytest.mark.asyncio
    async def test_get_voice(self):
        """Test get_voice returns voice dict."""
        service = VoiceClonerService()
        service._provider._temp_uris["test"] = "speech:test:model:123"
        voice = await service.get_voice("test")
        assert voice == {"name": "test", "uri": "speech:test:model:123"}

    @pytest.mark.asyncio
    async def test_get_voice_not_found(self):
        """Test get_voice returns None for missing voice."""
        service = VoiceClonerService()
        voice = await service.get_voice("nonexistent")
        assert voice is None

    @pytest.mark.asyncio
    async def test_delete_voice(self):
        """Test delete_voice delegates to provider."""
        service = VoiceClonerService()
        service._provider._temp_uris["test"] = "speech:test:model:123"
        result = await service.delete_voice("test")
        assert result is True
