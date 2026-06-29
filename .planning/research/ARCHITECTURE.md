# Architecture: Multi-Dimension Content Tracking (v5.1 Discover Rewrite)

**Project:** You2Bili
**Researched:** 2026-06-29
**Focus:** Integration points for keyword/creator/playlist/trending/topic tracking in existing FastAPI+Vue+SQLite architecture
**Confidence:** HIGH (based on thorough codebase analysis of all existing models, API routes, services, and frontend layers)

---

## Executive Summary

The existing codebase already has a partial scaffolding for discovery features from the deferred v4.0 milestone (models `DiscoverySource`, `DiscoveryResult`, `VideoScore` and APIs under `/api/discovery/`). However, there are critical gaps:

1. **`DiscoverySource.type`** only supports `channel | keyword | category | trending` — needs `playlist` and `topic` added.
2. **No APScheduler exists for DiscoverySource items** — only the `ChannelScanner` (for the `Channel` model) exists. DiscoverySource items have no automatic scanning.
3. **No per-source filter conditions** — filter fields (min_views, duration range) only exist on the `Channel` model, not on `DiscoverySource`.
4. **The current DiscoverView is built for the v4.0 scoring engine** — it uses `scoringApi.discover()` and `rulesApi`, both of which are deferred. It must be rewritten from scratch.
5. **No Pinia store for discovery** — the current view fetches data inline, no caching or state management.

The new architecture extends existing patterns. The `ChannelScanner` pattern (APScheduler + per-source jobs + scan logs) should be replicated for DiscoverySource. The frontend needs a dedicated `discoveryStore.ts` and a multi-tab DiscoverView.

---

## Existing Architecture (Before v5.1)

### Backend Models

| Model | Table | Key Fields | Used For |
|-------|-------|------------|----------|
| `Channel` | `channels` | name, url, enabled, scan_interval_hours, last_scanned_at, filter_min_views, filter_min/max_duration_sec | Creator/channel tracking (Phase 9) |
| `DiscoverySource` | `discovery_sources` | type (channel\|keyword\|category\|trending), source_value, label, enabled, last_scanned_at, scan_interval_hours, max_results_per_scan | v4.0 deferred discovery sources |
| `DiscoveryResult` | `discovery_results` | source_id (FK), youtube_id, title, channel_name, composite_score, status (new\|scored\|dubbed\|ignored), video_id (FK) | v4.0 deferred discovery results |
| `Video` | `videos` | youtube_id, title, channel, duration, view_count, thumbnail_url, status, channel_id (FK), source | Core video storage |
| `VideoScore` | `video_scores` | youtube_id, virality/translation/quality/market/cost/composite_score, category | v4.0 deferred scoring (out of scope) |
| `ScanLog` | `scan_logs` | channel_id (FK), scanned_at, found_count, added_count, error_msg | Channel scan history |

### Critical Observation: Two Parallel Tracking Systems

The codebase has **two independent tracking systems** that were never unified:

```
System A: Channel (Phase 9, actively used)
  Channel model → ChannelScanner (APScheduler) → Video + Task creation → ScanLog
  API: /api/channels/ (CRUD + scan-now + scan-logs)

System B: DiscoverySource (Phase 14, deferred v4.0)
  DiscoverySource model → run_discovery() (manual trigger only, no scheduler) → DiscoveryResult + VideoScore
  API: /api/discovery/sources/ (CRUD) + /api/discovery/sources/{id}/scan (manual)
```

v5.1 should **extend System A patterns** (APScheduler + logs) to cover all dimension types, rather than using System B.

### Existing Backend Services

| Service | File | Function |
|---------|------|----------|
| `YoutubeService` | `services/youtube.py` | yt-dlp wrapper: search, channel scan, video info, download (synchronous + async wrappers) |
| `ChannelScanner` | `services/channel_scanner.py` | APScheduler: per-channel IntervalTrigger jobs, `scan_once()` → filter → deduplicate → bulk_add → ScanLog |
| `discovery_pipeline.run_discovery()` | `services/scoring/discovery_pipeline.py` | Fetch from source → deduplicate → score → store DiscoveryResult + VideoScore (no scheduler, manual only) |
| `scoring.discovery.scrape_trending()` | `services/scoring/discovery.py` | yt-dlp subprocess: fetch trending videos by category |
| `scoring.metrics.fetch_video_metrics()` | `services/scoring/metrics.py` | YouTube Data API v3 or yt-dlp fallback for per-video metadata |
| `scoring.scorer.score_video()` | `services/scoring/scorer.py` | Five-dimension scoring (out of scope for v5.1, but usable for sorting) |

### Existing API Endpoints

| Method | Path | Purpose | Keep/Modify/Remove |
|--------|------|---------|---------------------|
| POST | `/api/discovery/search` | YouTube keyword search via yt-dlp | **KEEP** (manual search mode) |
| POST | `/api/discovery/channel` | Scan channel videos | **KEEP** (manual search mode) |
| POST | `/api/discovery/info` | Get single video info | **KEEP** |
| POST | `/api/discovery/add` | Batch add videos to DB | **KEEP** |
| POST | `/api/discovery/download` | Trigger download | **KEEP** |
| GET/POST/PUT/DELETE | `/api/discovery/sources[/{id}]` | CRUD for DiscoverySource | **KEEP** (add playlist/topic type) |
| POST | `/api/discovery/sources/{id}/scan` | Manual scan trigger | **KEEP** (extend to all types) |
| GET | `/api/discovery/results` | List results | **KEEP** |
| PUT | `/api/discovery/results/{id}/ignore` | Mark ignored | **KEEP** |
| POST | `/api/discovery/results/{id}/dub` | Create dub task | **KEEP** |
| GET | `/api/discovery/channels` | List tracked channels | **DEPRECATE** (use /api/channels) |
| GET/POST/PUT/DELETE | `/api/channels/` | Full channel CRUD | **KEEP** (creator tracking) |
| POST | `/api/channels/{id}/scan-now` | Trigger channel scan | **KEEP** |
| GET | `/api/channels/{id}/scan-logs` | Channel scan history | **KEEP** |
| GET | `/api/scoring/discover` | Auto-discover trending + scoring | **REMOVE** (v4.0 deferred) |
| GET | `/api/scoring/batch` | Batch scoring | **REMOVE** (v4.0 deferred) |
| GET | `/api/scoring/history` | Score history | **REMOVE** (v4.0 deferred) |

### Existing Frontend Layer

| File | Purpose | Status |
|------|---------|--------|
| `views/DiscoverView.vue` | Scored video grid + channel sidebar (v4.0 deferred) | **REWRITE** |
| `views/ChannelsView.vue` | Full channel CRUD table (F2 Phase 9) | **KEEP** (link from Discover) |
| `api/index.ts` | API client: `discoveryApi`, `scoringApi`, `channelApi`, `rulesApi` | **MODIFY** (remove scoringApi refs, add new endpoints) |
| `stores/` | No discovery store exists | **ADD** `discoveryStore.ts` |

---

## Proposed Architecture (v5.1)

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                       FRONTEND (Vue 3)                          │
│                                                                 │
│  DiscoverView.vue (REWRITE)                                     │
│  ┌──────────────────────────────────────────────────────┐      │
│  │  Tab: Search  |  Tab: Keywords  |  Tab: Creators    │      │
│  │  Tab: Playlists | Tab: Trending | Tab: Topics        │      │
│  │                                                      │      │
│  │  Search Bar + Filters (views, duration, date)        │      │
│  │  ┌──────────────────────────────────────────────┐    │      │
│  │  │  Results Grid (video cards + checkboxes)      │    │      │
│  │  └──────────────────────────────────────────────┘    │      │
│  │  ┌──────────────────────────────────────────────┐    │      │
│  │  │  Saved Tracking Sources (manage + scan status) │    │      │
│  │  └──────────────────────────────────────────────┘    │      │
│  └──────────────────────────────────────────────────────┘      │
│                                                                 │
│  Stores: discoveryStore.ts (NEW)                                │
│  - sources: active tracking sources                             │
│  - results: search results + scan results                       │
│  - filters: current filter state                                │
│  - actions: search, addSource, removeSource, triggerScan, etc.  │
│                                                                 │
│  API: discoveryApi (MODIFIED)                                   │
│  + search, source CRUD, scan, results, add-to-db                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     BACKEND (FastAPI)                            │
│                                                                 │
│  /api/v5/discovery/ (NEW prefix or extended)                    │
│  ├── POST   /search          — manual keyword search            │
│  ├── POST   /channel         — scan single channel              │
│  ├── POST   /playlist        — scan single playlist (NEW)       │
│  ├── POST   /trending        — fetch trending (NEW)             │
│  ├── POST   /topic           — topic search (NEW)               │
│  ├── POST   /add             — batch add to DB                  │
│  ├── POST   /download        — trigger download                 │
│  ├── GET    /sources         — list all sources                 │
│  ├── POST   /sources         — create source (extended types)   │
│  ├── PUT    /sources/{id}    — update source + filter           │
│  ├── DELETE /sources/{id}    — delete source                    │
│  ├── POST   /sources/{id}/scan  — trigger scan                  │
│  ├── GET    /results         — list results with filters        │
│  ├── POST   /results/batch-add  — add multiple to videos table  │
│  └── POST   /results/batch-ignore                               │
│                                                                 │
│  (Existing /api/channels/ kept for backward compatibility)      │
│                                                                 │
│  Models: DiscoverySource (MODIFIED), DiscoveryResult (KEEP)     │
│  Services: DiscoveryScanner (NEW, patterned after ChannelScanner)│
│            YoutubeService (KEEP, yt-dlp wrapper)                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                  ▼
┌────────────────────┐ ┌──────────────┐ ┌──────────────────┐
│  APScheduler        │ │  yt-dlp      │ │  SQLite DB       │
│  (DiscoveryScanner) │ │  (fetch)     │ │  (models)        │
│  - Per-source jobs  │ │              │ │                   │
│  - IntervalTrigger  │ │              │ │                   │
│  - ScanLog pattern  │ │              │ │                   │
└────────────────────┘ └──────────────┘ └──────────────────┘
```

### Data Flow

#### Flow A: Manual Search (ad-hoc)

```
User types query in search bar
  → Frontend: discoveryStore.search({ type, query, filters })
    → API POST /api/v5/discovery/search (or /channel, /playlist, /trending, /topic)
      → Backend: YoutubeService.search() via yt-dlp
      → Filter results server-side by view_count, duration, date
      → Return DiscoveryItem[]
    → Frontend: display in results grid
  → User selects videos → POST /api/discovery/add
  → User triggers download → POST /api/discovery/download
```

#### Flow B: Saved Tracking (automatic)

```
User saves a tracking source (e.g., keyword "tech review")
  → Frontend: discoveryStore.addSource({ type: "keyword", source_value: "tech review", ... })
    → API POST /api/v5/discovery/sources
      → Backend: DiscoverySource created in DB
      → DiscoveryScanner registers APScheduler job for this source
  → On schedule (IntervalTrigger, e.g., every 24h):
    → DiscoveryScanner dispatches by type:
      - keyword → yt-dlp ytsearch
      - creator → yt-dlp channel scan (or reuse Channel model)
      - playlist → yt-dlp playlist dump
      - trending → yt-dlp trending feed
      - topic → yt-dlp topic search
    → Filter results
    → Deduplicate against existing videos
    → Store as DiscoveryResult rows
    → Write ScanLog
  → User visits Discover page:
    → Frontend: GET /api/v5/discovery/results?source_id=X
    → Frontend: display new results with "new" badge
```

---

## Changes by Layer

### Layer 1: Models

#### `DiscoverySource` — MODIFY

Add types `playlist` and `topic` and add filter columns:

```python
class DiscoverySource(Base, TimestampMixin):
    __tablename__ = "discovery_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="keyword | creator | playlist | trending | topic",
    )
    source_value: Mapped[str] = mapped_column(
        String(512), nullable=False,
        comment="Keyword text / Channel URL / Playlist URL / topic name",
    )
    label: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="Human-readable name",
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scanned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    scan_interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    max_results_per_scan: Mapped[int] = mapped_column(Integer, default=20)

    # NEW: Filter conditions (nullable = no filter)
    filter_min_views: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    filter_max_views: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    filter_min_duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    filter_max_duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    filter_published_within_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True,
        comment="Only videos published within this many hours")
```

#### `DiscoveryResult` — MODIFY

Add richer metadata so the results grid can show thumbnail, view count, etc. without extra queries:

```python
class DiscoveryResult(Base, TimestampMixin):
    __tablename__ = "discovery_results"

    # ... existing fields keep ...

    # NEW: Richer metadata for results grid display
    duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    view_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    like_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    published_at: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
```

#### `ScanLog` — MODIFY (optional)

Currently tied to `channels` table via FK `channel_id`. For universal scan logging:

```python
# Option A: Add source_type and source_id columns to ScanLog
source_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

# Option B: Create a new UniversalScanLog model (preferred to avoid breaking existing code)
class DiscoveryScanLog(Base):
    __tablename__ = "discovery_scan_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("discovery_sources.id", ondelete="CASCADE"), index=True, nullable=False,
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), ...)
    found_count: Mapped[int] = mapped_column(Integer, default=0)
    added_count: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

**Recommendation:** Create `DiscoveryScanLog` to keep concerns separate from channel scanning. This adds a new table rather than modifying ScanLog.

#### No changes to: `Video`, `Channel`, `Task`, `Config`

### Layer 2: Services

#### New: `DiscoveryScanner` — patterned after `ChannelScanner`

```python
class DiscoveryScanner:
    """
    APScheduler-driven scanner for all DiscoverySource types.
    Mirrors ChannelScanner pattern: per-source IntervalTrigger jobs,
    scan_once() dispatches by type, writes DiscoveryScanLog.
    """

    JOB_ID_PREFIX = "discovery_scan_"

    def __init__(self, max_concurrent: int = 3):
        self._max_concurrent = max_concurrent
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def start(self) -> None:
        """Register jobs for all enabled DiscoverySources."""
        ...

    async def stop(self) -> None:
        """Shutdown scheduler."""
        ...

    def reschedule_source(self, source: DiscoverySource) -> None:
        """Update or remove job when source is modified."""
        ...

    async def scan_once(self, source_id: int) -> ScanResult:
        """Dispatch to type-specific fetcher → filter → deduplicate → store → log."""
        ...

    async def _fetch_and_filter(self, source: DiscoverySource) -> list[dict]:
        """Dispatch by type: keyword → search, creator → channel, playlist → playlist, etc."""
        if source.type == "keyword":
            return await self._search_keyword(source.source_value, source.max_results_per_scan)
        elif source.type == "creator":
            return await self._scan_channel(source.source_value, source.max_results_per_scan)
        elif source.type == "playlist":
            return await self._scan_playlist(source.source_value, source.max_results_per_scan)
        elif source.type == "trending":
            return await self._fetch_trending(source.max_results_per_scan)
        elif source.type == "topic":
            return await self._search_topic(source.source_value, source.max_results_per_scan)
        ...
```

#### Modified: `discovery_pipeline.run_discovery()`

Can be simplified since scoring is removed. The new flow is: fetch → filter → deduplicate → store DiscoveryResult (no VideoScore).

Alternatively, deprecate the old pipeline and use DiscoveryScanner exclusively.

#### Modified: `YoutubeService`

Add new methods:
- `get_playlist_videos(url, max_results)` — yt-dlp playlist dump
- `get_trending(category, max_results)` — yt-dlp trending feed (use browse IDs)

Both can use existing `_normalize_entry()`.

### Layer 3: API Routes

#### New endpoints or extension of existing `/api/discovery/` routes:

| Method | Path | Action | Notes |
|--------|------|--------|-------|
| POST | `/api/discovery/playlist` | Scan single playlist URL | Manual mode |
| POST | `/api/discovery/trending` | Fetch trending | Optional category query param |
| POST | `/api/discovery/topic` | Search by topic label | Uses yt-dlp search |
| POST | `/api/discovery/results/batch-add` | Add multiple results to Videos table | Accept list of result_id |
| POST | `/api/discovery/results/batch-ignore` | Mark multiple as ignored | Accept list of result_id |
| GET | `/api/discovery/sources/{id}/scan-logs` | Scan logs for a source | NEW DiscoveryScanLog |

#### Existing endpoint modifications:

- `POST /api/discovery/sources/` — accept `type: playlist | topic | keyword | creator | trending`
- `GET /api/discovery/sources/` — include filter fields in response
- `PUT /api/discovery/sources/{id}` — accept filter field updates

#### Endpoints to remove/deprecate:

- `GET /api/discovery/channels` — deprecated in favor of `/api/channels`
- `GET /api/scoring/discover` — remove entirely (v4.0 deferred, not part of v5.1)
- `GET /api/scoring/history` — remove entirely
- `POST /api/scoring/batch` — remove entirely

### Layer 4: Frontend Store

#### New: `frontend/src/stores/discoveryStore.ts`

```typescript
// Pattern: Composition API Pinia store (matching taskStore.ts)

export const useDiscoveryStore = defineStore('discovery', () => {
  // State
  const sources = ref<DiscoverySource[]>([])
  const searchResults = ref<DiscoveryItem[]>([])
  const scanResults = ref<DiscoveryResult[]>([])
  const loading = ref(false)
  const activeTab = ref<'search' | 'keywords' | 'creators' | 'playlists' | 'trending' | 'topics'>('search')

  // Filters
  const filters = ref({
    minViews: null as number | null,
    maxViews: null as number | null,
    minDuration: null as number | null,
    maxDuration: null as number | null,
    publishedWithin: null as number | null,  // hours
  })

  // Actions
  async function search(type: string, query: string, maxResults = 20) { ... }
  async function addSource(type: string, value: string, label: string, filters?: SourceFilters) { ... }
  async function removeSource(id: number) { ... }
  async function triggerScan(id: number) { ... }
  async function fetchSources() { ... }
  async function fetchResults(sourceId?: number) { ... }
  async function addToDB(resultIds: number[]) { ... }
  async function ignoreResults(resultIds: number[]) { ... }

  return { sources, searchResults, scanResults, loading, activeTab, filters, ... }
})
```

### Layer 5: Frontend View

#### `DiscoverView.vue` — COMPLETE REWRITE

**Layout:**
```
┌──────────────────────────────────────────────────────────┐
│ [Tab Bar: Search | Keywords | Creators | Playlists |    │
│            Trending | Topics]                            │
├──────────────────────────────────────────────────────────┤
│ (Search Tab)                                             │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ Search bar + type selector + filter row              │ │
│ └──────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ Results Grid (video cards)                           │ │
│ │ [thumbnail] [thumbnail] [thumbnail] [thumbnail]     │ │
│ │ [title]     [title]     [title]     [title]         │ │
│ │ [views/dur] [views/dur] [views/dur] [views/dur]    │ │
│ │ [ADD]       [ADD]       [ADD]       [ADD]           │ │
│ └──────────────────────────────────────────────────────┘ │
│                                                          │
│ (Other Tabs)                                             │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ Saved Sources List + Add Source Form                 │ │
│ │ [Keyword: tech review] [Scan: 2h ago] [Scan Now]    │ │
│ │ [Playlist: best of...] [Scan: never] [Scan Now]     │ │
│ │ [Add new...]                                         │ │
│ └──────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ Results for Selected Source (video cards)            │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key UI decisions:**
- Tab-based navigation for the six tracking dimensions
- Search tab is ad-hoc: no persistence, just keyword/URL input + filters + results
- Other five tabs show: (a) list of saved sources, (b) results from last scan
- Each result card has an "Add to My Videos" button
- Filter bar shows/hides based on tab

### Existing Files to Preserve

| File | Reason |
|------|--------|
| `backend/app/api/` (all current files) | Many routes still needed (videos, tasks, config, channels, platform, publish, dub, etc.) |
| `backend/app/services/channel_scanner.py` | Channel scanning still works. DiscoveryScanner is additive. |
| `backend/app/models/channel.py` | Existing channel model stays. For v5.1, `creator` sources in DiscoverySource can optionally link to Channel. |
| `frontend/src/views/ChannelsView.vue` | Full CRUD still relevant. DiscoverView can link to it. |
| `frontend/src/stores/taskStore.ts` | Unchanged. |
| `frontend/src/api/index.ts` (existing discoveryApi, channelApi blocks) | Keep. Add new methods. |

### Files to Remove

| File | Reason |
|------|--------|
| `backend/app/api/scoring.py` | Entire v4.0 scoring API out of scope |
| `backend/app/api/rules.py` | v4.0 rule engine deferred |
| `backend/app/api/analytics.py` | v4.0 analytics deferred |
| `backend/app/models/video_score.py` | (or keep as dormant table — no migration needed) |
| `backend/app/models/content_rule.py` | (or keep as dormant) |
| `backend/app/services/scoring/` entire directory | All v4.0 scoring services deferred |
| Frontend references to `scoringApi`, `rulesApi` in `api/index.ts` | Remove or mark deprecated |

### Router Registration Changes

In `backend/app/api/router.py`:
- Remove `scoring_router`, `rules_router`, `analytics_router` registrations (or comment out)
- Discovery routes remain under `/api/discovery/`

---

## Dependencies & Build Order

```
Phase 1: Backend Foundation
  ┌─────────────────────────────────────────────────────────┐
  │ 1.1 Models: Extend DiscoverySource (playlist, topic     │
  │     types, filter columns)                              │
  │ 1.2 Models: Extend DiscoveryResult (display metadata)   │
  │ 1.3 Models: Create DiscoveryScanLog table               │
  │ 1.4 Router: Remove scoring/rules/analytics from router  │
  └─────────────────────────────────────────────────────────┘
                              │
                              ▼
Phase 2: Backend Services
  ┌─────────────────────────────────────────────────────────┐
  │ 2.1 YoutubeService: Add get_playlist_videos()           │
  │ 2.2 YoutubeService: Add get_trending()                  │
  │ 2.3 DiscoveryScanner: Create (APScheduler scanner)      │
  │     - Per-source IntervalTrigger jobs                   │
  │     - Type dispatching (keyword/creator/playlist/etc)   │
  │     - Filter application                                │
  │     - Deduplication + DiscoveryResult storage           │
  │     - DiscoveryScanLog writing                          │
  │ 2.4 Service lifecycle: Wire DiscoveryScanner into       │
  │     FastAPI startup/shutdown (same as ChannelScanner)   │
  └─────────────────────────────────────────────────────────┘
                              │
                              ▼
Phase 3: Backend API
  ┌─────────────────────────────────────────────────────────┐
  │ 3.1 Extend POST /api/discovery/search (accept type      │
  │     param to route to keyword/playlist/trending/topic)  │
  │ 3.2 Extend /api/discovery/sources CRUD (accept new      │
  │     types, filter fields)                               │
  │ 3.3 POST /api/discovery/results/batch-add               │
  │ 3.4 POST /api/discovery/results/batch-ignore            │
  │ 3.5 GET /api/discovery/sources/{id}/scan-logs           │
  │ 3.6 Wire DiscoveryScanner scan to POST .../scan         │
  └─────────────────────────────────────────────────────────┘
                              │
                              ▼
Phase 4: Frontend Store & API Client
  ┌─────────────────────────────────────────────────────────┐
  │ 4.1 api/index.ts: Add new API methods                    │
  │     - discoveryApi.searchWithType()                      │
  │     - discoveryApi.playlist(), trending(), topic()       │
  │     - discoveryApi.batchAdd(), batchIgnore()             │
  │     - discoveryApi.sourceScanLogs()                      │
  │ 4.2 Remove/archive scoringApi, rulesApi from api/index   │
  │ 4.3 stores/discoveryStore.ts: Create (sources, results,  │
  │     filters, search, CRUD actions)                       │
  │ 4.4 stores/index.ts: Export discoveryStore               │
  └─────────────────────────────────────────────────────────┘
                              │
                              ▼
Phase 5: Frontend DiscoverView Rewrite
  ┌─────────────────────────────────────────────────────────┐
  │ 5.1 Tab bar component (6 tabs)                          │
  │ 5.2 Search tab: search bar + type selector + filters    │
  │ 5.3 Results grid component (reusable video cards)        │
  │ 5.4 Source management UI (list + add/edit/delete)       │
  │     per tab                                              │
  │ 5.5 Scan results per source (video cards from DB)       │
  │ 5.6 Batch add/ignore buttons                            │
  │ 5.7 Filter bar component                                │
  └─────────────────────────────────────────────────────────┘
                              │
                              ▼
Phase 6: Polish & Testing
  ┌─────────────────────────────────────────────────────────┐
  │ 6.1 Thumbnail fix (YouTube cover not displaying)        │
  │ 6.2 Download directory deduplication fix                │
  │ 6.3 End-to-end test: keyword source → auto scan →       │
  │     see results → add to videos → download              │
  │ 6.4 Loading states, error handling, empty states        │
  └─────────────────────────────────────────────────────────┘
```

### Why This Order

1. **Models first** — All downstream code depends on schema. Must add new types and columns before services touch them.
2. **Services second** — The scanner is the core logic. Building it before APIs means APIs can call real logic instead of stubs.
3. **API routes third** — Depends on both models and services. Adding endpoints after the service layer means they wire through directly.
4. **Frontend client + store fourth** — Store depends on API contract being stable.
5. **View rewrite fifth** — Depends on everything above being ready.
6. **Polish last** — Bug fixes for pre-existing issues should not block feature delivery.

### Parallelizable Work

- Phase 1.4 (router cleanup) and 2.1-2.2 (YoutubeService additions) can run in parallel with Phase 1.1-1.3 (model changes).
- Phase 5.2-5.4 (individual tab components) can be split across multiple developers.
- Phase 6.1-6.2 (thumbnail + dedup fixes) can be done at any point since they touch different code.

---

## Database Migration Strategy

Backward-compatible, additive migrations only:

1. `DiscoverySource` — ALTER TABLE to add columns with nullable defaults (no existing data affected)
2. `DiscoveryResult` — ALTER TABLE to add display metadata columns (nullable)
3. `DiscoveryScanLog` — CREATE TABLE (new, no migration needed for existing rows)

No destructive operations. The old `DiscoverySource.type` values (`channel`, `keyword`, `category`, `trending`) remain valid. The new types (`creator`, `playlist`, `topic`) are additive. The `category` type can be remapped to `topic` via a data migration or left as-is.

---

## References

- Existing `ChannelScanner`: `backend/app/services/channel_scanner.py` (pattern to replicate)
- Existing `DiscoverySource` model: `backend/app/models/discovery.py` (model to extend)
- Existing `DiscoverView.vue`: `frontend/src/views/DiscoverView.vue` (view to rewrite)
- Existing `ChannelsView.vue`: `frontend/src/views/ChannelsView.vue` (pattern reference for source management UI)
- Existing `taskStore.ts`: `frontend/src/stores/taskStore.ts` (Pinia store pattern to follow)
- Existing API client: `frontend/src/api/index.ts` (client to extend)
- Existing `YoutubeService`: `backend/app/services/youtube.py` (service to extend)
- Existing router: `backend/app/api/router.py` (router to modify)
- Context7 (yt-dlp): yt-dlp supports `--playlist-end N` and flat playlist extraction natively — confirmed via codebase analysis of existing `_ytdlp_json()` usage
