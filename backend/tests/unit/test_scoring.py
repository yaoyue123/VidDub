"""Unit tests for Phase 13 scoring engine."""
import json

import pytest

from app.services.scoring.scorer import (
    score_video,
    _score_virality,
    _score_translation,
    _score_quality,
    _score_market,
    _score_cost,
    DEFAULT_WEIGHTS,
    _validate_weights,
)


class TestViralityScorer:
    def test_basic_video(self):
        m = {"view_count": 100000, "like_count": 5000, "comment_count": 500,
             "published_at": "2026-06-25T00:00:00Z"}
        score = _score_virality(m)
        assert 0 <= score <= 100
        assert score > 30  # decent engagement

    def test_zero_views(self):
        m = {"view_count": 0, "like_count": 0, "comment_count": 0}
        assert _score_virality(m) == 0.0

    def test_missing_data(self):
        assert _score_virality({}) == 0.0

    def test_highly_viral(self):
        m = {"view_count": 10_000_000, "like_count": 500_000,
             "comment_count": 50_000,
             "published_at": "2026-06-25T12:00:00Z"}
        score = _score_virality(m)
        assert score > 60

    def test_old_video_penalty(self):
        m = {"view_count": 100_000, "like_count": 5000, "comment_count": 500,
             "published_at": "2025-01-01T00:00:00Z"}
        score = _score_virality(m)
        # Old video should score lower than fresh one with same stats
        fresh = {"view_count": 100_000, "like_count": 5000,
                 "comment_count": 500,
                 "published_at": "2026-06-25T00:00:00Z"}
        fresh_score = _score_virality(fresh)
        assert score <= fresh_score


class TestTranslationScorer:
    def test_ideal_translation_candidate(self):
        m = {"has_captions": True, "speaker_count": 1,
             "duration_sec": 600, "language": "en"}
        score = _score_translation(m)
        assert score > 80

    def test_no_captions_multi_speaker(self):
        m = {"has_captions": False, "speaker_count": 5,
             "duration_sec": 7200, "language": "fr"}
        score = _score_translation(m)
        assert score < 50

    def test_auto_captions(self):
        m = {"has_captions": "auto", "speaker_count": 1,
             "duration_sec": 600, "language": "en"}
        score = _score_translation(m)
        assert 50 <= score <= 90


class TestQualityScorer:
    def test_sweet_spot(self):
        m = {"duration_sec": 600, "view_count": 500_000,
             "title": "How to Build a PC - Complete Guide",
             "subscriber_count": 1_000_000}
        score = _score_quality(m)
        assert score > 70

    def test_short_clickbait(self):
        m = {"duration_sec": 30, "view_count": 100,
             "title": "YOU WON'T BELIEVE THIS!!!",
             "subscriber_count": 100}
        score = _score_quality(m)
        assert score < 40

    def test_score_in_range(self):
        m = {"duration_sec": 300, "view_count": 10_000,
             "title": "Normal title", "subscriber_count": 50_000}
        score = _score_quality(m)
        assert 0 <= score <= 100


class TestMarketScorer:
    def test_tech_category(self):
        score = _score_market({}, category="tech")
        assert score == 90.0

    def test_science_category(self):
        score = _score_market({}, category="science")
        assert score == 95.0

    def test_china_bonus(self):
        base = _score_market({}, category="tech")
        boosted = _score_market(
            {"title": "China tech innovation 2026", "tags": ["china"]},
            category="tech",
        )
        assert boosted > base

    def test_risk_penalty(self):
        base = _score_market({}, category="news")
        penalized = _score_market(
            {"title": "Political protest in Beijing", "tags": ["political"]},
            category="news",
        )
        assert penalized < base

    def test_unknown_category(self):
        score = _score_market({}, category="unknown")
        assert 40 <= score <= 60  # neutral


class TestCostScorer:
    def test_easy_video(self):
        m = {"has_captions": True, "speaker_count": 1,
             "category": "fitness", "subscriber_count": 1_000_000}
        score = _score_cost(m)
        assert score > 70

    def test_hard_video(self):
        m = {"has_captions": False, "speaker_count": 4,
             "category": "comedy", "subscriber_count": 1000}
        score = _score_cost(m)
        assert score < 40


class TestCompositeScore:
    def test_full_scoring(self):
        metrics = {
            "view_count": 500_000, "like_count": 25_000,
            "comment_count": 2_000,
            "published_at": "2026-06-25T00:00:00Z",
            "has_captions": True, "speaker_count": 1,
            "duration_sec": 600, "language": "en",
            "title": "How to Build a PC - Step by Step Guide",
            "subscriber_count": 1_000_000,
            "category": "tech",
        }
        result = score_video(metrics, category="tech")
        assert 0 <= result["composite_score"] <= 100
        assert result["virality_score"] > 0
        assert result["translation_score"] > 0
        assert result["market_score"] == 90.0
        assert "weights_used" in result
        assert "raw_metrics" in result

    def test_custom_weights(self):
        metrics = {
            "view_count": 500_000, "like_count": 25_000,
            "comment_count": 2_000,
            "published_at": "2026-06-25T00:00:00Z",
            "duration_sec": 600, "title": "Test",
        }
        custom = {"virality": 0.50, "translation": 0.20,
                  "quality": 0.10, "market": 0.10, "cost": 0.10}
        result = score_video(metrics, weights=custom)
        assert result["composite_score"] > 0
        weights_used = json.loads(result["weights_used"])
        assert weights_used["virality"] == 0.50

    def test_invalid_weights_raises(self):
        bad = {"virality": 1.0, "translation": 1.0}
        with pytest.raises(ValueError):
            _validate_weights(bad)

    def test_zero_view_video(self):
        metrics = {
            "view_count": 0, "like_count": 0, "comment_count": 0,
            "duration_sec": 300, "title": "New video",
        }
        result = score_video(metrics)
        assert result["virality_score"] == 0.0
        assert result["composite_score"] >= 0

    def test_all_scores_in_range(self):
        """All dimension scores must be 0-100."""
        metrics = {"view_count": 1000, "like_count": 50, "comment_count": 5,
                   "duration_sec": 600, "title": "Test", "language": "en"}
        result = score_video(metrics)
        for dim in ["virality_score", "translation_score", "quality_score",
                     "market_score", "cost_score", "composite_score"]:
            assert 0 <= result[dim] <= 100, f"{dim} out of range: {result[dim]}"


class TestDefaultWeights:
    def test_weights_sum_to_one(self):
        total = sum(DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01

    def test_validate_weights_ok(self):
        _validate_weights(DEFAULT_WEIGHTS)  # should not raise

    def test_validate_weights_bad(self):
        with pytest.raises(ValueError):
            _validate_weights({"a": 0.5, "b": 0.3})
