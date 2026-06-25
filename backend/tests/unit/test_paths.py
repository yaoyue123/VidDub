"""Unit tests for dubbing/paths.py — file paths and segment grouping."""
from app.services.dubbing.paths import group_segments_by_silence


class TestGroupSegmentsBySilence:
    """Tests for paragraph-level segment grouping (pipeline refactor)."""

    def test_empty_segments(self):
        """Empty list returns empty list."""
        assert group_segments_by_silence([]) == []

    def test_single_segment(self):
        """Single segment becomes one paragraph."""
        segments = [{"id": 0, "start": 0.0, "end": 2.5, "text": "Hello."}]
        result = group_segments_by_silence(segments)
        assert len(result) == 1
        assert result[0]["id"] == 0
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 2.5
        assert len(result[0]["segments"]) == 1
        assert result[0]["merged_text"] == "Hello."

    def test_no_gaps_all_one_paragraph(self):
        """Segments with gaps < threshold → all in one paragraph."""
        segments = [
            {"id": 0, "start": 0.0, "end": 2.0, "text": "A."},
            {"id": 1, "start": 2.5, "end": 4.0, "text": "B."},  # gap=0.5
            {"id": 2, "start": 4.5, "end": 6.0, "text": "C."},  # gap=0.5
        ]
        result = group_segments_by_silence(segments, threshold_sec=8.0)
        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 6.0
        assert len(result[0]["segments"]) == 3
        assert result[0]["merged_text"] == "A. B. C."

    def test_all_gaps_exceed_threshold(self):
        """Every gap >= threshold → each segment is its own paragraph."""
        segments = [
            {"id": 0, "start": 0.0, "end": 2.0, "text": "A."},
            {"id": 1, "start": 12.0, "end": 14.0, "text": "B."},  # gap=10.0
            {"id": 2, "start": 24.0, "end": 26.0, "text": "C."},  # gap=10.0
        ]
        result = group_segments_by_silence(segments, threshold_sec=8.0)
        assert len(result) == 3
        assert result[0]["id"] == 0
        assert result[1]["id"] == 1
        assert result[2]["id"] == 2
        assert result[0]["merged_text"] == "A."
        assert result[1]["merged_text"] == "B."
        assert result[2]["merged_text"] == "C."

    def test_mixed_gaps(self):
        """Some gaps split, some don't."""
        segments = [
            {"id": 0, "start": 0.0, "end": 2.0, "text": "A."},
            {"id": 1, "start": 2.5, "end": 4.0, "text": "B."},   # gap=0.5 → same para
            {"id": 2, "start": 14.0, "end": 16.0, "text": "C."},  # gap=10.0 → new para
            {"id": 3, "start": 16.5, "end": 18.0, "text": "D."},  # gap=0.5 → same para
        ]
        result = group_segments_by_silence(segments, threshold_sec=8.0)
        assert len(result) == 2
        # Paragraph 0: A + B
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 4.0
        assert len(result[0]["segments"]) == 2
        assert result[0]["merged_text"] == "A. B."
        # Paragraph 1: C + D
        assert result[1]["start"] == 14.0
        assert result[1]["end"] == 18.0
        assert len(result[1]["segments"]) == 2
        assert result[1]["merged_text"] == "C. D."

    def test_custom_threshold(self):
        """Custom threshold_sec is respected."""
        segments = [
            {"id": 0, "start": 0.0, "end": 2.0, "text": "A."},
            {"id": 1, "start": 5.0, "end": 7.0, "text": "B."},  # gap=3.0
        ]
        # With threshold 10 → one paragraph
        r1 = group_segments_by_silence(segments, threshold_sec=10.0)
        assert len(r1) == 1

        # With threshold 2 → two paragraphs
        r2 = group_segments_by_silence(segments, threshold_sec=2.0)
        assert len(r2) == 2

    def test_exact_threshold_boundary(self):
        """Gap exactly equals threshold → new paragraph."""
        segments = [
            {"id": 0, "start": 0.0, "end": 2.0, "text": "A."},
            {"id": 1, "start": 10.0, "end": 12.0, "text": "B."},  # gap=8.0 exactly
        ]
        result = group_segments_by_silence(segments, threshold_sec=8.0)
        assert len(result) == 2

    def test_gap_just_below_threshold(self):
        """Gap just below threshold → same paragraph."""
        segments = [
            {"id": 0, "start": 0.0, "end": 2.0, "text": "A."},
            {"id": 1, "start": 9.99, "end": 12.0, "text": "B."},  # gap=7.99
        ]
        result = group_segments_by_silence(segments, threshold_sec=8.0)
        assert len(result) == 1

    def test_mercged_text_excludes_empty(self):
        """Segments with empty/blank text are excluded from merged_text."""
        segments = [
            {"id": 0, "start": 0.0, "end": 2.0, "text": "Hello."},
            {"id": 1, "start": 2.5, "end": 4.0, "text": ""},
            {"id": 2, "start": 4.5, "end": 6.0, "text": "World."},
        ]
        result = group_segments_by_silence(segments, threshold_sec=8.0)
        assert len(result) == 1
        assert result[0]["merged_text"] == "Hello. World."

    def test_segments_without_id_field(self):
        """Segments without explicit id field still work."""
        segments = [
            {"start": 0.0, "end": 2.0, "text": "A."},
            {"start": 2.5, "end": 4.0, "text": "B."},
        ]
        result = group_segments_by_silence(segments)
        assert len(result) == 1
        assert len(result[0]["segments"]) == 2

    def test_preserves_segment_objects(self):
        """Original segment dicts are preserved in paragraph.segments (not copies)."""
        seg = {"id": 0, "start": 0.0, "end": 2.0, "text": "Hello.", "extra": "keep"}
        result = group_segments_by_silence([seg])
        assert result[0]["segments"][0] is seg
        assert result[0]["segments"][0]["extra"] == "keep"
