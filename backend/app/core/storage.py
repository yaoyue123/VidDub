"""Module-level cached download directory — single source of truth.

All code that resolves the download directory path MUST call
``get_download_dir()`` instead of reading ``settings.downloads_dir``
directly or using a fallback literal string.

``set_download_dir()`` is called once during application lifespan
from a DB Config query.  No runtime code path modifies the value
except ``invalidate_download_dir()`` (exported for config-change
hooks, not used in normal operation).
"""

import os

_download_dir: str | None = None


def get_download_dir() -> str:
    """Single source of truth for download directory.

    Returns cached value if set (via startup normalization or
    set_download_dir()), otherwise falls back to settings.downloads_dir
    as the default.
    """
    if _download_dir is not None:
        return _download_dir
    from app.core.config import settings

    return settings.downloads_dir


def set_download_dir(path: str) -> None:
    """Set the global download directory (called at startup).

    Normalizes to absolute path to prevent relative-path ambiguity.
    """
    global _download_dir
    _download_dir = os.path.normpath(os.path.abspath(path))


def invalidate_download_dir() -> None:
    """Clear cache so next get_download_dir() reads from settings fallback."""
    global _download_dir
    _download_dir = None
