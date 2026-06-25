"""
SiliconFlow Voice Cloner Provider.

Implements voice cloning using SiliconFlow Upload Voice API.
"""

import asyncio
import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL = settings.siliconflow_tts_model


def _get_api_key_sync() -> str:
    """Read API key from unified settings (single source of truth)."""
    return settings.siliconflow_api_key.strip()


class SiliconFlowVoiceCloner:
    """SiliconFlow voice cloning provider.

    Uploads audio to SiliconFlow to create voice clones for TTS.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model
        self._temp_uris: dict[str, str] = {}  # name -> uri mapping

    async def _ensure_api_key(self) -> str:
        """Ensure API key is available."""
        if self.api_key:
            return self.api_key
        key = _get_api_key_sync()
        if not key:
            raise RuntimeError(
                "SiliconFlow API key not configured. "
                "Set SILICONFLOW_API_KEY in backend/.env"
            )
        return key

    async def upload_voice(
        self,
        audio_path: str,
        custom_name: str,
        text: str,
    ) -> str:
        """Upload audio file to create a voice clone.

        Args:
            audio_path: Path to audio file (MP3, WAV, etc.).
            custom_name: User-defined name for the voice.
            text: Corresponding text content of the audio.

        Returns:
            URI string for use in TTS (e.g., "speech:name:model:id").

        Raises:
            FileNotFoundError: If audio file not found.
            RuntimeError: If upload fails.
        """
        import os

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        api_key = await self._ensure_api_key()

        with open(audio_path, "rb") as f:
            audio_data = f.read()

        # Determine MIME type
        ext = os.path.splitext(audio_path)[1].lower()
        mime_map = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".opus": "audio/opus",
            ".pcm": "audio/pcm",
        }
        mime_type = mime_map.get(ext, "audio/mpeg")
        filename = os.path.basename(audio_path)

        headers = {"Authorization": f"Bearer {api_key}"}

        async with httpx.AsyncClient(timeout=120.0) as client:
            files = {
                "file": (filename, audio_data, mime_type),
            }
            data = {
                "model": self.model,
                "customName": custom_name,
                "text": text,
            }

            try:
                upload_voice_url = f"{settings.siliconflow_base_url.rstrip('/')}/uploads/audio/voice"
                response = await client.post(
                    upload_voice_url,
                    files=files,
                    data=data,
                )
                response.raise_for_status()
                result = response.json()
                uri = result.get("uri", "")

                if not uri:
                    raise RuntimeError(f"No URI returned: {result}")

                # Store temporarily
                self._temp_uris[custom_name] = uri
                logger.info("Voice uploaded: %s -> %s", custom_name, uri)
                return uri

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    # Rate limit - retry after delay
                    logger.warning("Rate limited, retrying after delay...")
                    await asyncio.sleep(5)
                    return await self.upload_voice(audio_path, custom_name, text)
                raise RuntimeError(f"Upload failed: {e.response.status_code} {e.response.text}")
            except Exception as e:
                raise RuntimeError(f"Upload failed: {e}")

    async def get_uri(self, name: str) -> Optional[str]:
        """Get stored URI by name."""
        return self._temp_uris.get(name)

    async def list_voices(self) -> list[dict[str, str]]:
        """List temporarily stored voices."""
        return [{"name": name, "uri": uri} for name, uri in self._temp_uris.items()]

    async def delete_voice(self, name: str) -> bool:
        """Delete a temporarily stored voice URI."""
        if name in self._temp_uris:
            del self._temp_uris[name]
            logger.info("Voice deleted: %s", name)
            return True
        return False
