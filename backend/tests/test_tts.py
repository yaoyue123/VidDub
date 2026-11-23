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

    @pytest.mark.asyncio
    async def test_service_initialization(self, monkeypatch):
        """Test TTSService lazy initialization and provider selection."""
        from app.services.tts_new.service import TTSService
        from app.services.tts_new.siliconflow_provider import SiliconFlowTTSProvider

        async def _backend():
            return "siliconflow"

        monkeypatch.setattr("app.services.tts_new.service._get_tts_backend", _backend)

        service = TTSService()
        # Provider is selected lazily (backend comes from the DB config).
        assert service._provider is None
        provider = await service._get_provider()
        assert isinstance(provider, SiliconFlowTTSProvider)

    def test_service_custom_provider(self):
        """Test TTSService with custom provider."""
        from app.services.tts_new.service import TTSService

        mock_provider = MagicMock(spec=TTSProvider)
        service = TTSService(provider=mock_provider)
        assert service._provider is mock_provider


class TestVoiceNormalization:
    """Voices from one backend must not leak into another."""

    def test_edge_backend_rejects_siliconflow_voice(self):
        from app.services.tts_new.service import TTSService

        service = TTSService()
        service._backend = "edge-tts"
        assert service._normalize_voice("anna") is None
        assert service._normalize_voice("zh-CN-XiaoxiaoNeural") == "zh-CN-XiaoxiaoNeural"

    def test_siliconflow_backend_rejects_edge_voice(self):
        from app.services.tts_new.service import TTSService

        service = TTSService()
        service._backend = "siliconflow"
        assert service._normalize_voice("zh-CN-YunxiNeural") is None
        assert service._normalize_voice("anna") == "anna"

    def test_edge_provider_falls_back_for_invalid_voice(self):
        from app.services.tts_new.edge_tts_provider import EdgeTTSProvider

        provider = EdgeTTSProvider(voice="anna")
        assert provider._resolve_voice(None) == "zh-CN-XiaoxiaoNeural"
        assert provider._resolve_voice("zh-CN-YunxiNeural") == "zh-CN-YunxiNeural"


class TestMossTTSProvider:
    """MOSS-TTS-Nano local provider contract."""

    @pytest.mark.asyncio
    async def test_builtin_voices_include_chinese(self):
        from app.services.tts_new.moss_tts_provider import MossTTSProvider

        provider = MossTTSProvider()
        voices = await provider.get_available_voices()
        ids = {v["id"] for v in voices}
        assert {"Junhao", "Zhiming", "Weiguo", "Xiaoyu", "Yuewen", "Lingyu"} <= ids
        assert "Junhao" in ids

    @pytest.mark.asyncio
    async def test_missing_repo_raises_actionable_error(self, tmp_path):
        from app.services.tts_new.moss_tts_provider import MossTTSProvider

        provider = MossTTSProvider(repo_dir=str(tmp_path / "missing"))
        with pytest.raises(RuntimeError, match="MOSS-TTS-Nano not found"):
            await provider.synthesize("你好", str(tmp_path / "out.wav"))

    @pytest.mark.asyncio
    async def test_service_selects_moss_provider(self, monkeypatch):
        from app.services.tts_new.moss_tts_provider import MossTTSProvider
        from app.services.tts_new.service import TTSService

        async def _backend():
            return "moss"

        monkeypatch.setattr("app.services.tts_new.service._get_tts_backend", _backend)
        service = TTSService()
        assert isinstance(await service._get_provider(), MossTTSProvider)

    def test_moss_voice_normalization(self):
        from app.services.tts_new.service import TTSService

        service = TTSService()
        service._backend = "moss"
        assert service._normalize_voice("Junhao") == "Junhao"
        assert service._normalize_voice("zh-CN-XiaoxiaoNeural") is None
        assert service._normalize_voice("anna") is None
