"""Platforms package — central registry for publish/login platform metadata."""
from app.services.platforms.registry import (  # noqa: F401
    PlatformDescriptor,
    all_platforms,
    cookie_path,
    display_name,
    display_name_map,
    get,
)
