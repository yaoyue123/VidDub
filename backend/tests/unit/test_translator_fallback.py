"""Translation provider failure semantics and fallback."""
from unittest.mock import AsyncMock

import pytest

from app.services.translator import service as service_mod
from app.services.translator.base import TranslationProvider
from app.services.translator.service import TranslationService


class _FailingProvider(TranslationProvider):
    async def translate_segments(self, segments, source_lang="English", target_lang="Chinese", **kwargs):
        raise RuntimeError("429 Too Many Requests")

    async def translate_text(self, text, source_lang="English", target_lang="Chinese", **kwargs):
        raise RuntimeError("429 Too Many Requests")

    @property
    def is_available(self) -> bool:
        return True


class _FixedProvider(TranslationProvider):
    def __init__(self, value="你好"):
        self.value = value

    async def translate_segments(self, segments, source_lang="English", target_lang="Chinese", **kwargs):
        return [self.value for _ in segments]

    async def translate_text(self, text, source_lang="English", target_lang="Chinese", **kwargs):
        return self.value

    @property
    def is_available(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_google_failure_falls_back_to_siliconflow(monkeypatch):
    """A Google rate-limit error must not leak English into the dub."""
    monkeypatch.setattr(
        service_mod, "_get_translation_backend", AsyncMock(return_value="google"),
    )
    monkeypatch.setattr(
        service_mod, "_get_translation_model", AsyncMock(return_value="ignored"),
    )
    monkeypatch.setattr(
        "app.services.translator.google_provider.GoogleTranslateProvider",
        lambda: _FailingProvider(),
    )
    monkeypatch.setattr(
        service_mod, "SiliconFlowTranslationProvider",
        lambda model=None: _FixedProvider("你好"),
    )
    monkeypatch.setattr(
        "app.core.config.settings.siliconflow_api_key", "sk-test",
    )

    svc = TranslationService()
    out = await svc.translate_segments([{"text": "Hello"}])
    assert out == ["你好"]


@pytest.mark.asyncio
async def test_google_failure_without_key_raises(monkeypatch):
    """Without a SiliconFlow key the error must surface, never source text."""
    monkeypatch.setattr(
        service_mod, "_get_translation_backend", AsyncMock(return_value="google"),
    )
    monkeypatch.setattr(
        service_mod, "_get_translation_model", AsyncMock(return_value="ignored"),
    )
    monkeypatch.setattr(
        "app.services.translator.google_provider.GoogleTranslateProvider",
        lambda: _FailingProvider(),
    )
    monkeypatch.setattr(
        "app.core.config.settings.siliconflow_api_key", "",
    )

    svc = TranslationService()
    with pytest.raises(RuntimeError, match="429"):
        await svc.translate_segments([{"text": "Hello"}])


@pytest.mark.asyncio
async def test_google_provider_raises_instead_of_returning_source(monkeypatch):
    """The Google provider itself must raise on batch failure."""
    from app.services.translator import google_provider

    class _Boom:
        def __init__(self, *args, **kwargs):
            pass

        def translate_batch(self, texts):
            raise RuntimeError("quota exceeded")

        def translate(self, text):
            raise RuntimeError("quota exceeded")

    monkeypatch.setattr("deep_translator.GoogleTranslator", _Boom)

    provider = google_provider.GoogleTranslateProvider()
    with pytest.raises(RuntimeError, match="Google Translate failed"):
        await provider.translate_segments([{"text": "Hello"}])
