"""
SiliconFlow LLM translation provider.

Wraps the existing siliconflow.translate module into the TranslationProvider interface.
Retains the two-pass translate + polish strategy for high-quality subtitle translation.
"""

import logging
from typing import Any, Optional

import httpx

from app.services.siliconflow.client import get_async_client
from app.services.siliconflow.translate import (
    translate_segments as _sf_translate_segments,
    translate_text as _sf_translate_text,
)
from app.services.translator.base import TranslationProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4-Flash"


class SiliconFlowTranslationProvider(TranslationProvider):
    """Translate subtitles/text via SiliconFlow Chat API (LLM).

    Uses the existing two-pass translate + polish strategy.
    """

    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = get_async_client(timeout=120.0)
        return self._client

    async def translate_segments(
        self,
        segments: list[dict[str, Any]],
        source_lang: str = "English",
        target_lang: str = "Chinese",
        **kwargs,
    ) -> list[str]:
        """Translate segments using two-pass LLM translation.

        Args:
            segments: List of segment dicts with 'text' key.
            source_lang: Source language (passed to underlying translate module).
            target_lang: Target language (passed to underlying translate module).
            **kwargs: May include 'model' to override default model,
                      'context_window' for sliding window size.

        Returns:
            List of translated strings.
        """
        model = kwargs.get("model", self._model)
        context_window = int(kwargs.get("context_window", 2))

        client = await self._get_client()
        try:
            translations = await _sf_translate_segments(
                client, segments,
                model=model,
                context_window=context_window,
            )
            return translations
        except Exception as e:
            logger.error("SiliconFlow translate_segments failed: %s", e)
            raise RuntimeError(f"SiliconFlow translation failed: {e}") from e

    async def translate_text(
        self,
        text: str,
        source_lang: str = "English",
        target_lang: str = "Chinese",
        **kwargs,
    ) -> str:
        """Translate a single text string.

        Args:
            text: Text to translate.
            source_lang: Source language name.
            target_lang: Target language name.
            **kwargs: May include 'model' to override default model.

        Returns:
            Translated text.
        """
        model = kwargs.get("model", self._model)

        client = await self._get_client()
        try:
            translated = await _sf_translate_text(
                client, text,
                model=model,
                source_lang=source_lang,
                target_lang=target_lang,
            )
            return translated
        except Exception as e:
            logger.error("SiliconFlow translate_text failed: %s", e)
            raise RuntimeError(f"SiliconFlow text translation failed: {e}") from e

    @property
    def is_available(self) -> bool:
        """Check if the provider is available.

        SiliconFlow is available if API key is configured.
        """
        from app.core.config import settings
        return bool(settings.siliconflow_api_key.strip())

    async def close(self):
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
