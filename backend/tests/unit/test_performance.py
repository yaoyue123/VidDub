"""Unit tests for Phase 17 performance tracking."""
import pytest

from app.services.scoring.performance import calculate_actual_score


class TestActualScore:
    def test_bilibili_viral(self):
        score = calculate_actual_score(
            1_000_000, 50_000, 10_000, platform="bilibili",
        )
        assert 70 <= score <= 100

    def test_bilibili_low(self):
        score = calculate_actual_score(100, 5, 1, platform="bilibili")
        assert 0 <= score <= 30

    def test_zero_views(self):
        score = calculate_actual_score(0, 0, 0, platform="bilibili")
        assert score == 0.0

    def test_xigua_platform(self):
        score = calculate_actual_score(
            100_000, 5_000, 1_000, platform="ixigua",
        )
        assert 30 <= score <= 80

    def test_unknown_platform(self):
        score = calculate_actual_score(
            50_000, 2_000, 500, platform="unknown",
        )
        assert 0 <= score <= 100

    def test_all_scores_in_range(self):
        test_cases = [
            (0, 0, 0), (100, 1, 0), (1000, 10, 2),
            (10000, 100, 20), (100000, 1000, 200),
            (1000000, 50000, 10000),
        ]
        for views, likes, comments in test_cases:
            score = calculate_actual_score(views, likes, comments,
                                           platform="bilibili")
            assert 0 <= score <= 100, (
                f"views={views}: score={score}"
            )


class TestPerformanceModels:
    def test_model_import(self):
        from app.models.performance_log import PerformanceLog
        assert PerformanceLog.__tablename__ == "performance_logs"

    def test_model_fields(self):
        from app.models.performance_log import PerformanceLog
        assert hasattr(PerformanceLog, "video_id")
        assert hasattr(PerformanceLog, "platform")
        assert hasattr(PerformanceLog, "platform_views")
        assert hasattr(PerformanceLog, "predicted_score")
        assert hasattr(PerformanceLog, "actual_score")
        assert hasattr(PerformanceLog, "score_accuracy")
        assert hasattr(PerformanceLog, "fetch_method")
