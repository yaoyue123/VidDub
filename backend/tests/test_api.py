"""
Unit tests for API endpoints.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
import tempfile
import os

from app.main import app


client = TestClient(app)


class TestTranscriptionAPI:
    """Tests for Transcription API."""

    def test_transcription_providers_endpoint(self):
        """Test GET /api/transcription/providers."""
        response = client.get("/api/transcription/providers")
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert "whisper" in data["providers"]
        assert "siliconflow" in data["providers"]


class TestTTSAPI:
    """Tests for TTS API."""

    def test_tts_voices_endpoint(self):
        """Test GET /api/tts/voices."""
        response = client.get("/api/tts/voices")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "id" in data[0]
        assert "name" in data[0]

    def test_tts_models_endpoint(self):
        """Test GET /api/tts/models."""
        response = client.get("/api/tts/models")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "id" in data[0]
        assert "name" in data[0]

    def test_tts_synthesize_empty_text(self):
        """Test POST /api/tts with empty text returns 400."""
        response = client.post(
            "/api/tts",
            json={"text": ""},
        )
        assert response.status_code == 400

    def test_tts_synthesize_long_text(self):
        """Test POST /api/tts with too long text returns 400."""
        response = client.post(
            "/api/tts",
            json={"text": "x" * 10001},
        )
        assert response.status_code == 400


class TestVoiceCloneAPI:
    """Tests for Voice Clone API."""

    def test_voice_clone_list_endpoint(self):
        """Test GET /api/voice-clone."""
        response = client.get("/api/voice-clone")
        assert response.status_code == 200
        data = response.json()
        assert "voices" in data
        assert isinstance(data["voices"], list)

    def test_voice_clone_get_not_found(self):
        """Test GET /api/voice-clone/{name} returns 404."""
        response = client.get("/api/voice-clone/nonexistent")
        assert response.status_code == 404

    def test_voice_clone_delete_not_found(self):
        """Test DELETE /api/voice-clone/{name} returns 404."""
        response = client.delete("/api/voice-clone/nonexistent")
        assert response.status_code == 404
