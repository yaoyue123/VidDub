"""
Translation Service.

High-level service that provides config-based provider selection,
mirroring the pattern used by TranscriptionService and TTSService.
"""

import logging
from typing import Any, Optional

from app.core.database import async_session_factory
from app.models.config import Config
from app.services.translator.base import TranslationProvider
from app.services.translator.siliconflow_provider import SiliconFlowTranslationProvider

logger = logging.getLogger(__name__)


async def _get_translation_backend() -> str:
    """Read translation backend from DB config."""
    try:
        async with async_session_factory() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(Config).where(Config.key == "translation_backend")
            )
            config = result.scalar_one_or_none()
        return config.value if config else "siliconflow"
    except Exception:
        return "siliconflow"


async def _get_translation_model() -> str:
    """Read translation model from DB config."""
    try:
        async with async_session_factory() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(Config).where(Config.key == "translation_model")
            )
            config = result.scalar_one_or_none()
        return config.value if config else "deepseek-ai/DeepSeek-V4-Flash"
    except Exception:
        return "deepseek-ai/DeepSeek-V4-Flash"


class TranslationService:
    """High-level translation service with config-based provider selection.

    Automatically selects SiliconFlow or Google Translate based on configuration.
    """

    def __init__(self):
        self._provider: Optional[TranslationProvider] = None
        self._backend: Optional[str] = None

    async def _get_provider(self) -> TranslationProvider:
        """Get or create the appropriate provider based on config."""
        backend = await _get_translation_backend()
        model = await _get_translation_model()

        # Recreate provider if backend changed
        if self._backend != backend or self._provider is None:
            self._backend = backend

            if backend == "google":
                from app.services.translator.google_provider import GoogleTranslateProvider
                self._provider = GoogleTranslateProvider()
                logger.info("Using Google Translate translation provider")
            else:
                self._provider = SiliconFlowTranslationProvider(model=model)
                logger.info("Using SiliconFlow translation provider (model=%s)", model)

        return self._provider

    async def translate_segments(
        self,
        segments: list[dict[str, Any]],
        source_lang: str = "English",
        target_lang: str = "Chinese",
        **kwargs,
    ) -> list[str]:
        """Translate subtitle segments.

        Args:
            segments: List of segment dicts with 'text' key.
            source_lang: Source language name or code.
            target_lang: Target language name or code.
            **kwargs: Provider-specific options.

        Returns:
            List of translated strings.
        """
        provider = await self._get_provider()
        return await provider.translate_segments(
            segments,
            source_lang=source_lang,
            target_lang=target_lang,
            **kwargs,
        )

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
            source_lang: Source language name or code.
            target_lang: Target language name or code.
            **kwargs: Provider-specific options.

        Returns:
            Translated text.
        """
        provider = await self._get_provider()
        return await provider.translate_text(
            text,
            source_lang=source_lang,
            target_lang=target_lang,
            **kwargs,
        )
