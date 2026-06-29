"""Tests for Phase 9: DiscoverySource filter fields in schemas and endpoints."""

import pytest


class TestSourceFilterSchemas:
    """Verify filter field presence on DiscoverySource Pydantic schemas."""

    def test_discovery_source_create_has_filter_fields(self):
        """DiscoverySourceCreate should include all 5 filter fields."""
        from app.api.discovery import DiscoverySourceCreate

        s = DiscoverySourceCreate(type="keyword", source_value="test", label="test")
        assert hasattr(s, "filter_min_views")
        assert hasattr(s, "filter_max_views")
        assert hasattr(s, "filter_min_duration_sec")
        assert hasattr(s, "filter_max_duration_sec")
        assert hasattr(s, "filter_published_within_hours")
        # Default should be None (nullable)
        assert s.filter_min_views is None
        assert s.filter_max_views is None
        assert s.filter_min_duration_sec is None
        assert s.filter_max_duration_sec is None
        assert s.filter_published_within_hours is None

    def test_discovery_source_create_with_filter_values(self):
        """DiscoverySourceCreate should accept explicit filter values."""
        from app.api.discovery import DiscoverySourceCreate

        s = DiscoverySourceCreate(
            type="keyword", source_value="test", label="test",
            filter_min_views=1000, filter_max_views=100000,
            filter_min_duration_sec=60, filter_max_duration_sec=3600,
            filter_published_within_hours=48,
        )
        assert s.filter_min_views == 1000
        assert s.filter_max_views == 100000
        assert s.filter_min_duration_sec == 60
        assert s.filter_max_duration_sec == 3600
        assert s.filter_published_within_hours == 48

    def test_discovery_source_update_has_filter_fields(self):
        """DiscoverySourceUpdate should include all 5 filter fields as Optional."""
        from app.api.discovery import DiscoverySourceUpdate

        assert "filter_min_views" in DiscoverySourceUpdate.model_fields
        assert "filter_max_views" in DiscoverySourceUpdate.model_fields
        assert "filter_min_duration_sec" in DiscoverySourceUpdate.model_fields
        assert "filter_max_duration_sec" in DiscoverySourceUpdate.model_fields
        assert "filter_published_within_hours" in DiscoverySourceUpdate.model_fields

    def test_discovery_source_response_has_filter_fields(self):
        """DiscoverySourceResponse should include all 5 filter fields + id + timestamps."""
        from app.api.discovery import DiscoverySourceResponse

        assert "filter_min_views" in DiscoverySourceResponse.model_fields
        assert "filter_max_views" in DiscoverySourceResponse.model_fields
        assert "filter_min_duration_sec" in DiscoverySourceResponse.model_fields
        assert "filter_max_duration_sec" in DiscoverySourceResponse.model_fields
        assert "filter_published_within_hours" in DiscoverySourceResponse.model_fields
        assert "id" in DiscoverySourceResponse.model_fields
        assert "created_at" in DiscoverySourceResponse.model_fields
        assert "updated_at" in DiscoverySourceResponse.model_fields
        assert "enabled" in DiscoverySourceResponse.model_fields
        assert "last_scanned_at" in DiscoverySourceResponse.model_fields

    def test_discovery_source_response_has_from_attributes(self):
        """DiscoverySourceResponse should have from_attributes model_config for ORM mode."""
        from app.api.discovery import DiscoverySourceResponse

        assert DiscoverySourceResponse.model_config.get("from_attributes") is True
