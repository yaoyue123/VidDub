"""Bootstrap helpers for the `social-auto-upload` submodule.

The submodule ships `conf.example.py` but imports `conf` at package import
time.  `conf.py` is intentionally gitignored (it holds platform cookies), so
a fresh clone has no `conf.py` and every uploader import fails with
``ModuleNotFoundError: No module named 'conf'``.  Create it from the example
on first use so publishing works out of the box.
"""
from __future__ import annotations

import logging
import os
import shutil

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
SAU_DIR = os.path.join(_PROJECT_ROOT, "social-auto-upload")


def ensure_sau_conf() -> bool:
    """Create ``social-auto-upload/conf.py`` from the example if missing.

    Returns True when a usable ``conf.py`` exists.  Never raises: a missing
    submodule should surface later as a clear publisher error, not prevent the
    app (or unrelated tests) from starting.
    """
    if not os.path.isdir(SAU_DIR):
        return False

    conf_path = os.path.join(SAU_DIR, "conf.py")
    example_path = os.path.join(SAU_DIR, "conf.example.py")
    if not os.path.exists(conf_path) and os.path.exists(example_path):
        try:
            shutil.copyfile(example_path, conf_path)
            logger.info("Created social-auto-upload/conf.py from conf.example.py")
        except OSError as exc:
            logger.warning("Could not create social-auto-upload/conf.py: %s", exc)
            return False
    return os.path.exists(conf_path)
