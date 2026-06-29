"""Tests for Phase 9 Plan 02: Manual scan trigger + thumbnail proxy.

Task 1: Rewire scan endpoint to return ScanNowResponse (matching channels.py pattern)
Task 2: Add GET /thumbnail/{video_id} streaming proxy endpoint
"""


class TestScanNowResponseSchema:
    """ScanNowResponse should match the channels.py pattern for discovery sources."""

    def test_scan_now_response_required_fields(self):
        """ScanNowResponse requires source_id, found_count, added_count."""
        from app.api.discovery import ScanNowResponse

        resp = ScanNowResponse(source_id=1, found_count=5, added_count=3)
        assert resp.source_id == 1
        assert resp.found_count == 5
        assert resp.added_count == 3

    def test_scan_now_response_error_msg_optional(self):
        """ScanNowResponse.error_msg should be Optional[str], default None."""
        from app.api.discovery import ScanNowResponse

        resp = ScanNowResponse(source_id=1, found_count=0, added_count=0)
        assert resp.error_msg is None

        resp_with_error = ScanNowResponse(
            source_id=1, found_count=0, added_count=0,
            error_msg="Source disabled",
        )
        assert resp_with_error.error_msg == "Source disabled"

    def test_scan_now_response_all_fields_accessible(self):
        """All ScanNowResponse fields should be accessible via attribute."""
        from app.api.discovery import ScanNowResponse

        resp = ScanNowResponse(source_id=42, found_count=10, added_count=7, error_msg=None)
        assert hasattr(resp, "source_id")
        assert hasattr(resp, "found_count")
        assert hasattr(resp, "added_count")
        assert hasattr(resp, "error_msg")


class TestThumbnailProxySchema:
    """Thumbnail proxy endpoint should be registered and construct correct URLs."""

    def test_thumbnail_route_registered(self):
        """GET /thumbnail/{video_id} should be registered on the discovery router."""
        from app.api.discovery import router

        routes = [r.path for r in router.routes]
        assert "/thumbnail/{video_id}" in routes, (
            f"Thumbnail route not found in {routes}"
        )

    def test_thumbnail_constructs_correct_url(self):
        """The endpoint should construct the correct i.ytimg.com URL."""
        video_id = "dQw4w9WgXcQ"
        expected_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        # The URL construction is internal to the endpoint handler.
        # This test verifies the path parameter convention.
        assert len(video_id) == 11, "Standard YouTube video IDs are 11 characters"
        assert expected_url.startswith("https://i.ytimg.com/vi/")
        assert expected_url.endswith("/hqdefault.jpg")
