# Concerns

**Generated:** 2026-06-30
**Focus:** concerns

## Technical Debt

### 1. Social-auto-upload vendored but gitignored
**Severity:** CRITICAL
**File:** `.gitignore` line 35 (now fixed)
**Issue:** `social-auto-upload/` was gitignored despite being a vendored runtime dependency. A fresh `git clone` would be missing the entire publish backend, breaking the build.
**Status:** **FIXED** in commit 997b813 — blanket ignore removed, only `conf.py` remains ignored.

### 2. Empty `schemas/` directory
**Severity:** LOW
**Location:** `backend/app/schemas/`
**Issue:** Directory exists with only `__init__.py` and a `__pycache__/` — all Pydantic schemas are inlined in `api/*.py` modules. The empty directory is misleading.
**Recommendation:** Either populate with shared schemas or remove the directory.

### 3. Redundant `platforms/` (plural) directory
**Severity:** LOW
**Location:** `backend/app/services/platforms/`
**Issue:** Contains only `registry.py`. The actual platform login logic is in `platform/` (singular). The plural directory appears to be a leftover.
**Recommendation:** Remove `services/platforms/`, consolidate into `platform/`.

### 4. Stale test paths
**Severity:** MEDIUM
**Source:** ROADMAP.md (gitignored planning doc)
**Issue:** Some test file paths no longer exist or have been renamed. Tests reference outdated module locations.
**Recommendation:** Audit test imports against current codebase layout.

## Known Issues

### 5. Windows asyncio ProactorEventLoop workaround
**Severity:** MEDIUM
**Location:** `backend/start_server.py`, `backend/app/main.py`
**Issue:** uvicorn's `--loop none` flag is rejected by its CLI validator. On Windows, `ProactorEventLoop` is required for `create_subprocess_exec()` used by Playwright. The workaround uses a custom launcher script that sets the event loop policy programmatically.
**Fragility:** Any change to uvicorn version or startup method could break Playwright subprocess execution on Windows.

### 6. Whisper first-run download (~1.5GB)
**Severity:** LOW (UX friction)
**Location:** `backend/app/services/whisper_service.py`
**Issue:** The tiny Whisper model (~1.5GB) is downloaded automatically on first STT invocation. Users with slow connections experience long delays before first use. No progress indication during download.
**Recommendation:** Add download progress logging and an option to pre-download models during setup.

### 7. Platform login DOM fragility
**Severity:** MEDIUM
**Location:** `backend/app/services/platform/bilibili.py`, `douyin.py`, etc.
**Issue:** Playwright-based login automation depends on CSS selectors and DOM structure of each platform's login page. Any layout change by the platform breaks the login flow. No automated detection of selector changes.
**Recommendation:** Add selector versioning or self-healing selectors.

## Security

### 8. No CI/CD pipeline
**Severity:** MEDIUM
**Issue:** No `.github/workflows/` — no automated security scanning, dependency auditing, or linting in CI. Security relies entirely on manual review.
**Recommendation:** Add GitHub Actions with at minimum: `pip audit` / `npm audit`, linting, and test execution.

### 9. SQLite for production
**Severity:** MEDIUM
**Issue:** SQLite with WAL mode works well for single-user scenarios but won't scale to concurrent multi-user access. No migration path to PostgreSQL/MySQL documented.
**Recommendation:** Document supported deployment scale (single-user / small team). Add SQLAlchemy hooks for easy database backend swap.

### 10. No remote configured
**Severity:** LOW (infrastructure)
**Issue:** Local git repo has no remote. The project exists only on this machine.
**Status:** **FIXED** — remote `origin` added pointing to `https://github.com/yaoyue123/VidDub.git`.

## Performance

### 11. Sequential pipeline processing
**Severity:** LOW
**Issue:** The dubbing pipeline processes videos sequentially (one at a time) controlled by `asyncio.Semaphore` and `max_concurrent` config. No parallel processing within a single video's pipeline stages.
**Trade-off:** Deliberate design choice — reduces complexity and resource contention.

### 12. Large Whisper model memory usage
**Severity:** LOW
**Issue:** Whisper models (especially small/medium) consume significant RAM during transcription. On CPU-only systems, transcription is slow. No model unloading between tasks.
**Workaround:** Users can configure `whisper_model: tiny` in app_config for lower memory usage.

## Operational

### 13. No health check endpoint
**Severity:** LOW
**Issue:** Docker health check is not configured in `docker-compose.yml`. Container orchestration has no way to verify service readiness.
**Recommendation:** Add a `/health` endpoint (exists in `main.py` but not exposed) and configure Docker health check.

### 14. Docs may be stale
**Severity:** MEDIUM
**Issue:** README.md and docs/ARCHITECTURE.md reference v5.0 and list 20 API modules (actual: 16 routers in `router.py`). The project is at v5.1 but many docs still say v5.0.
**Recommendation:** Audit all docs vs current code after each milestone.
