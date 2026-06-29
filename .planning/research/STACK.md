# Technology Stack — v5.1 Discover Page Reconstruction and Bug Fixes

**Project:** you2bili
**Researched:** 2026-06-29
**Mode:** Subsequent milestone — additions/changes to existing stack
**Overall confidence:** HIGH

## Executive Summary

v5.1 does NOT need any new major framework or library. All required capabilities (multi-dimension tracking, filtering, trending, playlist extraction, thumbnail proxying) are achievable with the **existing stack**: yt-dlp for all YouTube data extraction, APScheduler for scheduling scans, FastAPI for backend API, Vue 3 + Element Plus for frontend, SQLite for persistence. The changes are additive: new database models, new API endpoints, new frontend views, and (critically) a **single-package addition** (httpx for thumbnail proxying is already in requirements.txt) and a **version bump** for yt-dlp. The duplicate download directory bug is a configuration normalization fix, not a dependency change.

## Recommended Stack Changes

### Version Bumps Required

| Package | Current | Recommended | Reason |
|---------|---------|-------------|--------|
| yt-dlp | `>=2024.12.0` | `>=2026.6.9` | YouTube anti-scraping changes break older versions regularly. Nightly channel recommended. Renamed stable releases use `YYYY.M.D` format. Use `--pre` flag or pin to `yt-dlp>=2026.6.9`. |

Rationale: yt-dlp is under constant development because YouTube changes its internal API structure every few weeks. The existing pin `>=2024.12.0` is 6 months stale and risks breaking `extract_flat` behavior for playlists/trending pages. The latest stable as of June 2026 is `2026.6.9`. The project's own documentation recommends the nightly channel (`--pre`) for regular users because stable releases become stale.

### New Python Dependencies: NONE

Every new feature can be built with existing dependencies:

| Capability | Existing Tool | How |
|------------|---------------|-----|
| Keyword tracking search | yt-dlp `ytsearch{N}:{query}` | Already implemented in `YoutubeService.search_sync()` |
| Creator/channel tracking | yt-dlp channel URL extraction | Already implemented in `YoutubeService.get_channel_videos_sync()` |
| Playlist tracking | yt-dlp playlist URL extraction | Trivial extension — same `extract_info()` with `extract_flat=True` |
| Trending | yt-dlp `https://www.youtube.com/feed/trending` | Extract as flat playlist — no special extractor needed |
| Topic/category | yt-dlp search + category filter | Search with topic keywords, or optional YouTube Data API v3 |
| Thumbnail proxy | httpx (already in requirements.txt) | FastAPI stream response proxying `i.ytimg.com` |
| Scheduling auto-scans | APScheduler (already in requirements.txt) | Extend `ChannelScanner` pattern to also scan keywords/playlists/trending/topics |

### Existing Stack That Stays Unchanged

| Layer | Technology | Version | v5.1 Change |
|-------|------------|---------|-------------|
| Backend framework | FastAPI | 0.115.0 | No change |
| ASGI server | uvicorn | 0.30.0 | No change |
| ORM | SQLAlchemy (asyncio) | 2.0.35 | No change |
| Async SQLite | aiosqlite | 0.20.0 | No change |
| Migrations | Alembic | 1.13.0 | No change (new models need migration) |
| Settings | pydantic-settings | 2.5.0 | No change |
| WebSocket | websockets | 13.0 | No change |
| HTTP client | httpx | >=0.28.1 | No change (used for thumbnail proxy) |
| Scheduler | APScheduler | >=3.10 | No change (extend usage) |
| Frontend framework | Vue 3 | ^3.5.13 | No change |
| Router | vue-router | ^4.5.0 | No change |
| State management | Pinia | ^2.3.0 | No change |
| UI library | Element Plus | ^2.9.0 | No change |
| Icons | @element-plus/icons-vue | ^2.3.1 | No change |
| HTTP client (FE) | axios | ^1.7.9 | No change |

## New Database Models Required

These are NOT library additions — they are new SQLAlchemy models that extend the existing `Base`.

### TrackedSource (replaces/enhances DiscoverySource)

The existing `DiscoverySource` model (in `app/models/discovery.py`) has a `type` field limited to `channel | keyword | category | trending`. This needs to be extended to support:

- **`keyword`** — search terms to scan periodically
- **`creator`** — YouTube channel/creator handles and URLs
- **`playlist`** — full YouTube playlist URLs
- **`trending`** — trending feed with optional region/category
- **`topic`** — topic-based discovery (optional YouTube Data API integration)

The existing `DiscoverySource` table already has a solid schema (`type`, `source_value`, `label`, `enabled`, `last_scanned_at`, `scan_interval_hours`, `max_results_per_scan`). v5.1 should extend it with:

- `region` (optional, for trending)
- `category_id` (optional, for trending/topic)
- `sort_by` (optional, default: "date" — for keyword search sorting)

### Filter/Sort Configuration

Add filter fields to the scan request/response objects (not a separate model):

- `min_views` — minimum view count filter
- `max_views` — maximum view count filter
- `min_duration_sec` — minimum video duration
- `max_duration_sec` — maximum video duration
- `published_after` — publish date lower bound
- `published_before` — publish date upper bound
- `sort_by` — one of: `date`, `views`, `duration`, `relevance` (for search)
- `sort_order` — `asc` or `desc`

## YouTube Thumbnail Bug: Root Cause and Fix

### Root Cause

The existing `_normalize_entry()` in `YoutubeService` stores `thumbnail_url` as the direct YouTube thumbnail CDN URL (`https://i.ytimg.com/vi/{id}/hqdefault.jpg`). The frontend renders this in `<img :src="thumbnail_url">`. The problem: `i.ytimg.com` does NOT serve CORS headers, and modern browsers enforce CORS for cross-origin image loading when the image is used in certain contexts. Additionally, YouTube's CDN may block requests without proper `Referer` headers. Some users behind restrictive networks or using privacy extensions will see broken thumbnails.

### Fix: Backend Thumbnail Proxy

Add a FastAPI endpoint that fetches the thumbnail server-side and serves it with proper CORS headers:

```
GET /api/discovery/thumbnail/{youtube_id}  ->  proxied image from i.ytimg.com
```

Implementation:
```python
from fastapi.responses import StreamingResponse
import httpx

@router.get("/thumbnail/{youtube_id}")
async def proxy_thumbnail(youtube_id: str):
    url = f"https://i.ytimg.com/vi/{youtube_id}/hqdefault.jpg"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        return StreamingResponse(
            resp.aiter_bytes(),
            media_type=resp.headers.get("content-type", "image/jpeg"),
            headers={
                "Cache-Control": "public, max-age=86400",
                "Access-Control-Allow-Origin": "*",
            },
        )
```

This uses `httpx` which is already in `requirements.txt`. No new dependency.

### Frontend Change

Replace direct YouTube CDN URLs with proxied URLs in thumbnail display. The `thumbnail_url` field in `Video` model can either:
- (A) Store the YouTube URL as-is and proxy at display time — requires frontend rewrite of all `<img :src>` references
- (B) Store the proxied URL at creation time — simpler but couples storage to proxy path
- (C) Normalize at API response level — add a `thumbnail_proxy_url` computed field

Recommendation: **Option C** with a Pydantic computed field. Add `thumbnail_proxy_url: str` to all video response schemas that represents `/api/discovery/thumbnail/{youtube_id}`. This keeps the database clean (stored URL remains the canonical YouTube URL for portability) while the frontend gets a working URL.

## Duplicate Download Directory Bug: Root Cause and Fix

### Root Cause

There are **two competing sources of truth** for the download directory:

1. **`settings.downloads_dir`** in `app/core/config.py` — default `"./downloads"` from `.env`
2. **DB Config key `download_dir`** — default `"./downloads"` from `config_seeder.py`

Multiple points read one or the other inconsistently:
- `main.py` line 88 reads **DB Config** `download_dir` for `TaskScheduler` constructor
- `main.py` line 31 reads **Settings** `downloads_dir` for static file mount (indirectly — line 88 uses DB config)
- `discovery.py` API reads **DB Config** `download_dir`
- `videos.py` API reads **DB Config** `download_dir`
- `scheduler.py` constructor has its own **hardcoded default** `"./downloads"` (line 167)
- `cli.py` passes **hardcoded** `"./downloads"` (lines 113, 250)
- `youtube.py.__init__` has its own **hardcoded default** `"./downloads"` (line 68)

When a user changes `download_dir` in the Settings UI (which updates DB Config), some paths use the new value while others continue using the old default. When `settings.downloads_dir` is set differently from DB Config's `download_dir`, the system creates/uses **two different directories**, leading to download failures, missing file references, and duplicate storage.

### Fix: Single Source of Truth

1. **Normalize at startup**: In `main.py` lifespan, ensure `Settings.downloads_dir` and DB Config `download_dir` are synchronized. Always prefer DB Config (user-adjustable via UI) as the truth, and write it back to a runtime setting.
2. **Remove hardcoded defaults**: All service constructors should accept `download_dir` as a parameter (not a default). The `TaskScheduler` and `YoutubeService` constructors should NOT have fallback defaults; they should be passed the directory from the single source.
3. **Create a `get_download_dir()` helper**: A single function that reads from DB Config with `Settings.downloads_dir` as a startup fallback. All code paths call this instead of duplicating logic.
4. **Config change hook**: When the user updates `download_dir` via Settings UI, invalidate any cached value and reinitialize affected services (likely just `YoutubeService` instances that cache the path).

### Implementation

```python
# app/core/storage.py (new file)
from app.core.config import settings

_download_dir: str | None = None

def get_download_dir() -> str:
    """Single source of truth for download directory."""
    return _download_dir or settings.downloads_dir

def set_download_dir(path: str) -> None:
    global _download_dir
    _download_dir = path
```

Or simpler: just always read from DB Config at point of use (since the cost is one query, and `download_dir` is already loaded in most request handlers' `_get_config_map()`).

## New API Endpoints Required

No new libraries needed — these are new FastAPI routes on existing or new routers.

| Endpoint | Method | Purpose | Router |
|----------|--------|---------|--------|
| `/api/discovery/search` | POST | Advanced search with filtering/sorting | Existing `discovery` router |
| `/api/discovery/trending` | POST | Fetch trending videos by region/category | Existing `discovery` router |
| `/api/discovery/playlist` | POST | Extract videos from a playlist URL | Existing `discovery` router |
| `/api/discovery/sources` | GET/POST/PUT/DELETE | CRUD for tracked sources (extends existing) | Existing `discovery` router |
| `/api/discovery/sources/{id}/scan` | POST | Trigger scan of one tracking source | Existing `discovery` router |
| `/api/discovery/scan-all` | POST | Scan all enabled tracking sources | Existing `discovery` router |
| `/api/discovery/thumbnail/{youtube_id}` | GET | Proxy YouTube thumbnail | Existing `discovery` router |
| `/api/discovery/results` | GET | List discovery results with filters | Existing `discovery` router |

## Frontend Component Architecture

No new npm packages needed. Vue 3 + Element Plus + axios covers all requirements.

### New/Modified Views

| View | Purpose | Type |
|------|---------|------|
| `DiscoverView.vue` | Complete rewrite — multi-tab discover page | **Rewrite** |
| `TrackingManager.vue` | Component for managing tracked sources (keywords/creators/playlists/trending/topics) | **New** |
| `SearchPanel.vue` | Manual search with filter/sort controls | **New** |
| `TrackedSourceCard.vue` | Display card for a tracked source | **New** |

### Element Plus Components to Use

All already available in `element-plus@^2.9.0`:

- `ElTabs` / `ElTabPane` — for switching between discovery modes (Search / Keywords / Creators / Playlists / Trending)
- `ElTable` — for displaying tracked sources list
- `ElPagination` — for paginated results
- `ElForm` / `ElFormItem` — for filter/sort controls
- `ElSelect` / `ElOption` — for sort-by, sort-order dropdowns
- `ElInputNumber` — for view count / duration range inputs
- `ElDatePicker` — for publish date range filter
- `ElTag` — for displaying tracking source type badges
- `ElPopconfirm` — for delete source confirmation
- `ElSwitch` — for enable/disable tracked sources
- `ElInput` / `ElButton` — for adding new tracked sources
- `ElCollapse` / `ElCollapseItem` — for filter panel expansion

### Pinia Store Additions

| Store | Purpose |
|-------|---------|
| `discoveryStore.ts` | State for discovery results, filters, tracked sources, loading states |

**New file** — not a modification of existing stores. Keeps concerns separated.

### API namespace additions

Add a `trackingApi` namespace to `frontend/src/api/index.ts` (following existing pattern of `discoveryApi`, `channelApi`, etc.):

```typescript
export interface TrackedSource { /* ... */ }
export interface DiscoveryResultWithMeta { /* ... */ }
export interface SearchFilter { /* ... */ }

export const trackingApi = {
  createSource(body: TrackedSourceCreate) { /* ... */ },
  listSources(params?: SourceFilter) { /* ... */ },
  updateSource(id: number, body: Partial<TrackedSourceCreate>) { /* ... */ },
  deleteSource(id: number) { /* ... */ },
  scanSource(id: number) { /* ... */ },
  scanAll() { /* ... */ },
  searchYouTube(query: string, filters: SearchFilter) { /* ... */ },
  getTrending(region?: string, category?: string) { /* ... */ },
  getPlaylistVideos(url: string) { /* ... */ },
  thumbnailUrl(youtubeId: string): string { /* ... */ },
}
```

## Scheduling Architecture for Auto-Scan

The existing `ChannelScanner` pattern (APScheduler `AsyncIOScheduler` + per-channel interval jobs) should be **generalized** to support all tracking source types.

### Current Design (ChannelScanner in `app/services/channel_scanner.py`)

- `ChannelScanner` manages APScheduler jobs for channel scanning only
- Each channel gets an interval job via `_register_job(channel)`
- Jobs run `scan_once(channel_id)` which calls `YoutubeService.get_channel_videos()`
- Results are filtered, deduped, and inserted as `Video` records with `source="channel"`

### v5.1 Design: SourceScanner (or extend ChannelScanner)

No new library needed. The existing `AsyncIOScheduler` can handle all scan types.

| Source Type | yt-dlp Method | Output Processing |
|-------------|---------------|-------------------|
| keyword | `ytsearch{N}:{query}` | Same as current search |
| creator | `get_channel_videos(channel_url)` | Same as current ChannelScanner |
| playlist | `extract_info(playlist_url, extract_flat=True)` | Iterate `entries` |
| trending | `extract_info(trending_url, extract_flat=True)` | Iterate `entries` |
| topic | `ytsearch{N}:{topic} sort:view_count` | Search sorted by relevance |

### Key Architecture Decision: One Scheduler or Separate?

**Recommendation: Extend `ChannelScanner` to `SourceScanner`** rather than creating a separate scanner for each type. All source types share:
- The same `AsyncIOScheduler` instance
- Same interval trigger pattern
- Same dedup/insert logic
- Same `ScanLog`-style logging

The difference is only in the extraction method. A `scan_type` -> `extractor_fn` mapping keeps it clean.

## What NOT to Add

| Library | Why Not |
|---------|---------|
| `youtube-trending-mcp` | Unnecessary abstraction — yt-dlp can extract `/feed/trending` directly. Adds a dependency for a 10-line function. |
| `pytube` | yt-dlp is already the standard, more maintained, more feature-complete. |
| `google-api-python-client` (YouTube Data API v3) | Requires API key, rate limits, OAuth. yt-dlp scraping is sufficient for a personal tool. Add only if topic/category taxonomy becomes critical. |
| Any charting library beyond echarts | Feature backlog item, not needed for discover page. |
| `vue-query` / `@tanstack/vue-query` | Overhead for a project with straightforward data fetching. Existing axios + manual ref handling is sufficient. |
| `pinia-plugin-persistedstate` | Discover page state is transient (search results, filters). No persistence needed. |
| Any CSS framework beyond Element Plus | Element Plus covers all needed components (tabs, tables, forms, date pickers). Adding Tailwind or similar is unnecessary scope creep. |

## Integration Points

| New Component | Integrates With | Integration Mechanism |
|---------------|-----------------|----------------------|
| SourceScanner | Existing `ChannelScanner` pattern | Refactor/extend `channel_scanner.py` |
| Thumbnail proxy | Existing `YoutubeService` | New FastAPI endpoint, uses httpx |
| New models | Existing `Base`, Alembic | New model files, Alembic migration |
| Tracking API | Existing `discovery` router | New endpoints on existing `APIRouter` |
| DiscoverView | Existing `api/index.ts` patterns | New `trackingApi` namespace |
| Filters | Existing `SearchRequest` schema | Extend Pydantic models |

## Sources

- [yt-dlp PyPI — latest versions 2026.6.9](https://pypi.org/project/yt-dlp/)
- [yt-dlp GitHub — module guide for playlist/trending extraction](https://github.com/yt-dlp/yt-dlp)
- Existing codebase analysis: `backend/app/services/youtube.py`, `backend/app/services/channel_scanner.py`, `backend/app/services/scheduler.py`, `backend/app/api/discovery.py`, `frontend/src/api/index.ts`, `frontend/src/views/DiscoverView.vue`
- `backend/app/core/config.py` lines 31-32 (downloads_dir source)
- `backend/app/services/youtube.py` line 68 (hardcoded default)
- `backend/app/services/scheduler.py` line 167 (hardcoded default)
- `backend/app/main.py` lines 88, 94, 111-121 (download_dir split between DB config and Settings)
