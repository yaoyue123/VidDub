"""
Google Translate free translation provider.

Uses the deep-translator library to access Google Translate's free web API.
No API key required — completely free for basic use.

Note: Rate limits apply for heavy usage. For production volume,
consider Google Cloud Translation API (paid, higher quota).
"""

import logging
from typing import Any, Optional

from app.services.translator.base import TranslationProvider

logger = logging.getLogger(__name__)

# Language code mapping: our names → Google Translate codes
LANG_MAP = {
    "English": "en",
    "Chinese": "zh-CN",
    "Japanese": "ja",
    "Korean": "ko",
    "Russian": "ru",
    "French": "fr",
    "German": "de",
    "Spanish": "es",
    "Italian": "it",
    "Portuguese": "pt",
    "Arabic": "ar",
    "Hindi": "hi",
    "en": "en",
    "zh": "zh-CN",
    "ja": "ja",
    "ko": "ko",
    "ru": "ru",
    "fr": "fr",
    "de": "de",
    "es": "es",
}


def _to_google_code(lang: str) -> str:
    """Map language name/code to Google Translate language code."""
    return LANG_MAP.get(lang, lang)


class GoogleTranslateProvider(TranslationProvider):
    """Translate text via Google Translate free web API.

    Uses deep-translator under the hood. No API key needed.

    Limitations:
    - Rate limited: ~5 requests/second per IP
    - Not suitable for high-volume production without rotation
    - Less accurate than LLM-based translation for creative content
    """

    def __init__(self):
        self._available: Optional[bool] = None

    async def translate_segments(
        self,
        segments: list[dict[str, Any]],
        source_lang: str = "English",
        target_lang: str = "Chinese",
        **kwargs,
    ) -> list[str]:
        """Translate segments using Google Translate.

        Each segment is translated individually via the free API.
        For long segments lists, a small delay is added between
        batches to avoid rate limiting.

        Args:
            segments: List of segment dicts with 'text' key.
            source_lang: Source language.
            target_lang: Target language.
            **kwargs: May include 'batch_size' (default 10) for
                     concurrent translation batch size.

        Returns:
            List of translated strings.
        """
        import asyncio

        source = _to_google_code(source_lang)
        target = _to_google_code(target_lang)
        batch_size = int(kwargs.get("batch_size", 10))

        from deep_translator import GoogleTranslator

        try:
            translator = GoogleTranslator(source=source, target=target)
        except Exception as e:
            logger.error("Failed to init GoogleTranslator: %s", e)
            raise RuntimeError(f"Google Translate init failed: {e}") from e

        results: list[str] = []
        texts = [seg.get("text", "").strip() for seg in segments]

        # Translate in batches with small delay between batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            # Filter empty texts
            non_empty = [(j, t) for j, t in enumerate(batch) if t]
            if not non_empty:
                results.extend(batch)
                continue

            batch_indices = [item[0] for item in non_empty]
            batch_texts = [item[1] for item in non_empty]

            try:
                if len(batch_texts) == 1:
                    translated = translator.translate(batch_texts[0])
                    batch_results = [translated]
                else:
                    batch_results = translator.translate_batch(batch_texts)
            except Exception as e:
                logger.warning(
                    "Google Translate batch failed (offset=%d): %s — falling back to source",
                    i, e,
                )
                batch_results = batch_texts  # fallback to source

            # Reconstruct full batch with empty slots
            full_results: list[str] = list(batch)  # copy original
            for idx_in_batch, result in zip(batch_indices, batch_results):
                full_results[idx_in_batch] = result or batch[idx_in_batch]

            results.extend(full_results)

            # Small delay between batches to avoid rate limiting
            if i + batch_size < len(texts):
                await asyncio.sleep(0.3)

        return results

    async def translate_text(
        self,
        text: str,
        source_lang: str = "English",
        target_lang: str = "Chinese",
        **kwargs,
    ) -> str:
        """Translate a single text string using Google Translate.

        Args:
            text: Text to translate.
            source_lang: Source language.
            target_lang: Target language.
            **kwargs: (unused)

        Returns:
            Translated text.
        """
        if not text or not text.strip():
            return text

        source = _to_google_code(source_lang)
        target = _to_google_code(target_lang)

        from deep_translator import GoogleTranslator

        try:
            translator = GoogleTranslator(source=source, target=target)
            result = translator.translate(text)
            return result or text
        except Exception as e:
            logger.warning("Google Translate text failed: %s — returning source", e)
            return text

    @property
    def is_available(self) -> bool:
        """Google Translate free API is always available (no key needed).

        If availability check fails, caches the result.
        """
        if self._available is not None:
            return self._available

        try:
            from deep_translator import GoogleTranslator
            GoogleTranslator(source="en", target="zh-CN")
            self._available = True
        except Exception:
            logger.warning("Google Translate not available (deep-translator may need install)")
            self._available = False

        return self._available
