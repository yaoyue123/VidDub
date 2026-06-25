"""Unit tests for Phase 14 discovery engine."""
import pytest

from app.services.scoring.discovery import (
    mine_keywords,
    TRENDING_CATEGORIES,
)


class TestKeywordMiner:
    def test_basic_keywords(self):
        keywords = mine_keywords(["tech", "education"])
        assert len(keywords) > 0
        assert all("keyword" in kw for kw in keywords)
        assert all("rationale" in kw for kw in keywords)

    def test_empty_categories(self):
        keywords = mine_keywords([])
        assert len(keywords) > 0  # defaults to tech, education, science

    def test_all_keywords_unique(self):
        keywords = mine_keywords(["tech", "education", "science"])
        kw_texts = [kw["keyword"] for kw in keywords]
        assert len(kw_texts) == len(set(kw_texts))

    def test_unknown_category_ignored(self):
        keywords = mine_keywords(["nonexistent"])
        assert len(keywords) > 0  # defaults kick in

    def test_max_results(self):
        keywords = mine_keywords(["tech", "education", "science",
                                   "fitness", "gaming"])
        assert len(keywords) <= 20


class TestTrendingCategories:
    def test_all_categories_defined(self):
        assert "tech" in TRENDING_CATEGORIES
        assert "science" in TRENDING_CATEGORIES
        assert "gaming" in TRENDING_CATEGORIES
        assert "music" in TRENDING_CATEGORIES
        assert len(TRENDING_CATEGORIES) == 4


class TestDiscoveryModels:
    def test_models_import(self):
        from app.models.discovery import DiscoverySource, DiscoveryResult
        assert DiscoverySource.__tablename__ == "discovery_sources"
        assert DiscoveryResult.__tablename__ == "discovery_results"

    def test_source_fields(self):
        from app.models.discovery import DiscoverySource
        assert hasattr(DiscoverySource, "type")
        assert hasattr(DiscoverySource, "source_value")
        assert hasattr(DiscoverySource, "label")
        assert hasattr(DiscoverySource, "enabled")
        assert hasattr(DiscoverySource, "scan_interval_hours")

    def test_result_fields(self):
        from app.models.discovery import DiscoveryResult
        assert hasattr(DiscoveryResult, "youtube_id")
        assert hasattr(DiscoveryResult, "status")
        assert hasattr(DiscoveryResult, "composite_score")
        assert hasattr(DiscoveryResult, "source_id")
