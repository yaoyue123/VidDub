"""Custom uvicorn launcher script.

uvicorn's CLI --loop flag only accepts [auto|asyncio|uvloop], but the internal
Config.LOOP_SETUPS dict also supports "none" (mapped to None), which makes
setup_event_loop() skip event loop configuration entirely.

We need this on Windows because:
1. uvicorn --reload sets use_subprocess=True
2. This triggers asyncio_setup() which sets SelectorEventLoopPolicy on Windows
3. SelectorEventLoop does not support create_subprocess_exec() (used by
   patchright/Playwright)
4. We need ProactorEventLoop instead

By passing loop="none" programmatically (not via CLI), we skip uvicorn's loop
setup and let the ProactorEventLoopPolicy remain in effect.

Usage:
    python start_server.py
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        loop="none",  # Skip uvicorn's loop setup; keep ProactorEventLoopPolicy
    )
