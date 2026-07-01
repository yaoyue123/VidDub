"""
Translation provider abstract base class.

Defines the interface for translation providers (SiliconFlow, Google Translate, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TranslationSegment:
    """A single translation segment with source text."""
    id: int
    text: str
    translated_text: Optional[str] = None


@dataclass
class TranslationResult:
    """Result from a translation operation."""
    translations: list[str]
    segments: list[TranslationSegment] = field(default_factory=list)
    source_lang: Optional[str] = None
    target_lang: Optional[str] = None


class TranslationProvider(ABC):
    """Abstract base class for translation providers.

    All translation backends (SiliconFlow LLM, Google Translate, etc.)
    must implement this interface.
    """

    @abstractmethod
    async def translate_segments(
        self,
        segments: list[dict[str, Any]],
        source_lang: str = "English",
        target_lang: str = "Chinese",
        **kwargs,
    ) -> list[str]:
        """Translate a list of subtitle segments.

        Args:
            segments: List of dicts with 'text' key (and optional 'start', 'end').
            source_lang: Source language name or code.
            target_lang: Target language name or code.
            **kwargs: Provider-specific options.

        Returns:
            List of translated strings, same order as input segments.

        Raises:
            RuntimeError: If translation fails.
        """
        pass

    @abstractmethod
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

        Raises:
            RuntimeError: If translation fails.
        """
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available (API key configured, etc.)."""
        pass
