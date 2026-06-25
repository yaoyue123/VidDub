"""
Voice Cloner Service.

High-level service for voice cloning operations.
"""

import logging
from typing import Optional

from app.services.voice_cloner.siliconflow_provider import SiliconFlowVoiceCloner

logger = logging.getLogger(__name__)


class VoiceClonerService:
    """High-level voice cloning service.

    Provides a unified interface for voice cloning operations.
    """

    def __init__(self, provider: Optional[SiliconFlowVoiceCloner] = None):
        self._provider = provider or SiliconFlowVoiceCloner()

    async def clone_voice(
        self,
        audio_path: str,
        custom_name: str,
        text: str,
    ) -> dict:
        """Clone a voice from an audio file.

        Args:
            audio_path: Path to audio file.
            custom_name: User-defined name for the voice.
            text: Corresponding text content of the audio.

        Returns:
            Dict with 'uri' and 'name' keys.
        """
        uri = await self._provider.upload_voice(audio_path, custom_name, text)

        return {
            "uri": uri,
            "name": custom_name,
        }

    async def list_voices(self) -> list[dict]:
        """List all available voices.

        Returns:
            List of voice dicts with 'name' and 'uri' keys.
        """
        return await self._provider.list_voices()

    async def get_voice(self, name: str) -> Optional[dict]:
        """Get a voice by name.

        Args:
            name: Voice name.

        Returns:
            Voice dict or None if not found.
        """
        uri = await self._provider.get_uri(name)
        if uri:
            return {"name": name, "uri": uri}
        return None

    async def delete_voice(self, name: str) -> bool:
        """Delete a voice.

        Args:
            name: Voice name.

        Returns:
            True if deleted, False if not found.
        """
        return await self._provider.delete_voice(name)
