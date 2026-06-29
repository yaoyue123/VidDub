# Project Research Summary

**Project:** you2bili
**Domain:** YouTube-to-Bilibili content discovery and tracking (v5.1 milestone)
**Researched:** 2026-06-29
**Confidence:** HIGH

## Executive Summary

This project is a cross-platform content repurposing pipeline (YouTube to Bilibili) with a personal-tool scope. v5.1 delivers a multi-dimension content tracking and discovery system -- allowing users to search, track, filter, and manage YouTube videos across five dimensions: keyword search, creator/channel monitoring, playlist extraction, trending feeds, and topic-based discovery. The existing codebase already has partial scaffolding from a deferred v4.0 milestone (DiscoverySource model, DiscoveryResult model, Yt-dlp service, APScheduler), but critical gaps exist: no automatic scanning for DiscoverySource items, no per-source filters, the DiscoverView is built for a scoring engine that no longer exists, and the system has two parallel tracking architectures that were never unified.

The recommended approach extends proven existing patterns (ChannelScanner's APScheduler + IntervalTrigger + ScanLog architecture) rather than introducing new frameworks. No new Python or npm dependencies are needed: all features build on yt-dlp, FastAPI, Vue 3, Element Plus, APScheduler, httpx, and SQLite already present. The key additions are: a generalized DiscoveryScanner service, a shared global yt-dlp rate limiter, SQLite WAL mode and targeted indexes, FTS5 for keyword search, and a complete frontend rewrite of DiscoverView into a multi-tab tracking dashboard.

The three critical risks are: (1) YouTube rate limiting taking down all tracking dimensions simultaneously without a shared rate limiter, (2) SQLite query degradation under new tracking query patterns without WAL mode and proper indexes, and (3) YouTube extractor changes breaking all five tracking dimensions at once without a centralized yt-dlp wrapper and version pinning. All three have clear mitigations that must be implemented early in the build order.

## Key Findings

### Recommended Stack

**No new dependencies required.** All v5.1 features build on the existing stack. The only changes are a yt-dlp version bump and extending existing patterns (no new libraries, no new frameworks, no new npm packages).

**Core technologies (unchanged from current):**
- **yt-dlp >=2026.6.9**: All YouTube data extraction (search, channel, playlist, trending) -- single dependency for the entire discovery pipeline. Bump from >=2024.12.0 required because YouTube changes break older versions frequently.
- **FastAPI 0.115.x**: Backend API framework. New endpoints extend existing discovery router; no new routers needed.
- **SQLAlchemy 2.0 + aiosqlite**: Database layer. New models (DiscoverySource extensions, DiscoveryScanLog) are additive, non-destructive migrations.
- **APScheduler >=3.10**: Job scheduling. Extend ChannelScanner pattern to a generalized DiscoveryScanner with a single coordinator loop.
- **httpx >=0.28.1**: Already in requirements.txt. Used for thumbnail proxying (no new dependency).
- **Vue 3 + Element Plus + Pinia**: Frontend stack. New discoveryStore.ts follows existing taskStore.ts pattern. No new npm packages.

**Explicitly NOT adding:**
- YouTube Data API v3 (google-api-python-client) -- yt-dlp scraping is sufficient; API key + rate limits are unnecessary overhead for a personal tool.
- Any charting/chart library -- feature backlog item, not needed for v5.1.
- vue-query/pinia-plugin-persistedstate -- existing axios + Pinia is sufficient for straightforward data fetching.
- Any CSS framework beyond Element Plus -- scope creep.

### Expected Features

**Must have (table stakes):**
- Keyword search with instant results and ability to save as tracked source
- Creator/channel tracking (already exists, needs unification into DiscoverySource model)
- Playlist URL extraction and tracking with order-preserving results
- Trending feed fetching by region with periodic snapshots
- Per-source filter conditions (min/max views, duration range, publish window)
- Deduplication against already-seen and already-downloaded videos
- One-click "add to pipeline" from discovery results
- Scan history and last-scanned timestamp per tracking source

**Should have (differentiators):**
- Per-keyword filter conditions (extends existing Channel filter pattern to DiscoverySource)
- Trending ranking position badge in results
- Multi-keyword topic tracking (topic = label + one or more search keywords)
- Thumbnail proxy fix (backend proxying i.ytimg.com through FastAPI with CORS headers)
- Download directory deduplication fix (single source of truth for download_dir)
- Cross-dimension dedup with source badges (same video found via keyword + trending)
- Bulk keyword import (textarea with line parsing)
- Auto-disable tracking sources that error repeatedly (consecutive failure threshold)

**Defer (post-v5.1):**
- AI-powered content relevance scoring (v4.0 deferred, out of scope)
- Trending real-time feed (scheduled snapshots at 4h intervals are sufficient)
- YouTube Data API v3 integration (only if topic/category taxonomy becomes critical)
- Automated channel suggestion/recommendation
- Predictive virality scoring for Chinese market
- Multi-user tracking workspaces

### Architecture Approach

The codebase has two parallel tracking systems that were never unified: System A (Channel model + ChannelScanner + APScheduler, actively used) and System B (DiscoverySource model + manual scan only, deferred from v4.0). The recommended approach extends System A's proven patterns to all tracking dimensions rather than building on System B's partial implementation.

A new DiscoveryScanner service (patterned after ChannelScanner) provides a single APScheduler coordinator loop that iterates all active DiscoverySource items by type (keyword, creator, playlist, trending, topic), dispatches to type-specific yt-dlp extraction, applies per-source filters, deduplicates against existing records, stores results as DiscoveryResult rows, and writes DiscoveryScanLog entries. A unified YtDlpWrapper centralizes all yt-dlp calls with shared cookie management, rate limiting, and extractor args. The frontend is a complete rewrite of DiscoverView.vue into a six-tab interface (Search, Keywords, Creators, Playlists, Trending, Topics) backed by a dedicated discoveryStore.ts Pinia store.

**Major components:**
1. **DiscoveryScanner** (new service) -- APScheduler coordinator, single loop scanning all source types, patterned after existing ChannelScanner
2. **YtDlpWrapper** (new/consolidated service) -- Centralized yt-dlp wrapper with shared rate limiter, cookie management, circuit breaker, and extractor-args configuration
3. **DiscoverySource model** (extended) -- Unified tracking source with five types, per-source filter columns, plan to merge Channel model
4. **DiscoveryResult model** (extended) -- Richer metadata for results grid display (duration, views, likes, thumbnail, publish date)
5. **DiscoveryScanLog** (new model) -- Scan history for discovery sources (separate from Channel's ScanLog)
6. **DiscoverView.vue** (rewrite) -- Six-tab interface with search bar, filter panel, results grid, and source management
7. **discoveryStore.ts** (new Pinia store) -- Sources, results, filters, loading state, CRUD actions
8. **Thumbnail proxy endpoint** -- FastAPI streaming proxy for i.ytimg.com with CORS headers and caching

### Critical Pitfalls

1. **yt-dlp Rate Limiting Without Backpressure:** The new tracking system fires yt-dlp requests across five dimensions concurrently. Without a shared global rate limiter, YouTube responds with 429/403 throttling that takes down ALL extraction (not just the triggering dimension). **Mitigation:** Single global sliding-window rate limiter with circuit breaker and --sleep-requests applied uniformly across all yt-dlp calls.

2. **SQLite Query Pattern Degradation:** New query patterns (keyword search, time-range filters, aggregation) become sequential scans on unindexed tables at 10,000+ records. The current database.py has no WAL mode, no busy_timeout, no index strategy. **Mitigation:** WAL mode + busy_timeout at connection setup, create indexes for all new query patterns before writing data, use FTS5 for keyword search, batch page-size-aware queries with LIMIT/OFFSET.

3. **YouTube Extractor Changes Cascade:** YouTube changes its InnerTube API ~4+ times per year. Each change can break all five tracking dimensions simultaneously. No version pinning exists. **Mitigation:** Pin yt-dlp version, create centralized YtDlpWrapper used by ALL tracking services, store extractor-args in DB Config table for hotfix without code deploy, add /api/health/yt-dlp-test endpoint.

4. **APScheduler Job Proliferation:** Per-source jobs multiply (10 keywords + 5 channels + 3 playlists = 18 jobs). Without coordinated scheduling, all jobs fire simultaneously at interval boundaries (thundering herd), saturating the DB connection pool and hitting rate limits. **Mitigation:** Single coordinator loop iterating all targets sequentially (preferred), or per-target jobs with jitter, misfire_grace_time=None, coalesce=True.

5. **Keyword Tracking Without FTS5 Becomes Unusable:** `WHERE title LIKE '%keyword%'` is a full table scan on 10,000+ videos. **Mitigation:** Use SQLite FTS5 virtual table with triggers to keep sync with videos table. Fall back to simple LIKE only for exact-match queries with guaranteed small result sets.

6. **Playlist Tracking Downloads Everything:** First scan of a 5000-video playlist floods the UI. **Mitigation:** --playlist-end N (start with N=5, paginate on demand), max_new_per_scan cap, store last-scanned position for incremental scans.

7. **Trending/Topic Tracking Hardcodes US Locale:** Default trending region is US English, useless for Chinese content creators. **Mitigation:** Per-target region config with TW/HK default, never assume server locale matches target audience.

8. **Frontend Tracking Config State Conflicts:** Single Pinia store with flat reactive state causes cross-tab dirty state overwrites. **Mitigation:** Per-dimension local draft form state with explicit save, per-tab isDirty tracking, beforeRouteLeave guard.

## Implications for Roadmap

Based on combined research, the recommended phase structure respects dependency chains (models before services, services before API, API before frontend) while addressing critical infrastructure early.

### Phase 1: Backend Foundation -- Models and Infrastructure
**Rationale:** All downstream code depends on schema. Must add new types and columns before services or APIs. Critical infrastructure (rate limiter, WAL mode, indexes, yt-dlp wrapper) must exist before any feature code touches yt-dlp or the database.
**Delivers:** Extended DiscoverySource model with playlist/topic types + filter columns, richer DiscoveryResult model, new DiscoveryScanLog table, DB indexes for tracking queries, WAL mode pragmas at connection setup, FTS5 virtual table for keyword search, shared yt-dlp rate limiter, centralized YtDlpWrapper, router cleanup (removing v4.0 scoring/rules/analytics).
**Addresses features:** DiscoverySource unification (merge Channel capabilities), per-source filter config, DB performance foundation.
**Avoids pitfalls:** Pitfall #2 (SQLite query degradation), Pitfall #3 (extractor breakage cascade), Pitfall #1 (rate limiting without backpressure).

### Phase 2: DiscoveryScanner Service and YouTube Service Extensions
**Rationale:** The scanner is the core logic. Building it before APIs means API endpoints can call real logic instead of stubs. The new DiscoveryScanner pattern (single coordinator loop with type-dispatch) eliminates the APScheduler job proliferation risk before it starts.
**Delivers:** DiscoveryScanner service with single APScheduler coordinator loop, type-dispatch to yt-dlp extraction methods (keyword, creator, playlist, trending, topic), per-source filter application, deduplication + DiscoveryResult storage, DiscoveryScanLog writing, YoutubeService extensions (get_playlist_videos, get_trending), service lifecycle wiring into FastAPI startup/shutdown.
**Addresses features:** Auto-scan scheduling for all tracking dimensions, scan history, dedup pipeline.
**Avoids pitfalls:** Pitfall #4 (APScheduler job proliferation -- single coordinator), Pitfall #1 (rate limiting -- built into YtDlpWrapper), Pitfall #15 (lazy yt-dlp flag inheritance -- centralized wrapper).

### Phase 3: Backend API Endpoints
**Rationale:** Depends on both models and services. Adding endpoints after the service layer means they wire through directly without stubs or TODOs.
**Delivers:** Extended search endpoint (accepts type param for keyword/playlist/trending/topic), extended DiscoverySource CRUD with new types and filter fields, batch-add/batch-ignore endpoints for DiscoveryResult, scan-logs endpoint, thumbnail proxy endpoint, scanner trigger wiring.
**Addresses features:** Manual search in all dimensions, source CRUD, batch pipeline operations.
**Avoids pitfalls:** Pitfall #6 (download dir state mutation -- thumbnail proxy on separate endpoint with rate limiting).

### Phase 4: Frontend Store and API Client
**Rationale:** Depends on stable API contract from Phase 3. Store implementation follows existing taskStore.ts pattern.
**Delivers:** discoveryStore.ts (sources, searchResults, scanResults, filters, loading state, all CRUD actions), trackingApi namespace in api/index.ts, removal/archival of scoringApi and rulesApi references.
**Addresses features:** Frontend state management for all tracking dimensions.
**Avoids pitfalls:** Pitfall #10 (state conflicts -- clean separation of concern in dedicated store).

### Phase 5: DiscoverView Complete Rewrite
**Rationale:** Largest frontend effort, depends on everything above being ready. The current view is built for the v4.0 scoring engine and must be rewritten from scratch.
**Delivers:** Six-tab interface (Search, Keywords, Creators, Playlists, Trending, Topics), search bar with type selector and filter row, reusable results grid component (video cards with thumbnails, metadata, add/ignore buttons), per-tab source management (list + add/edit/delete), scan results display, filter bar with show/hide, batch operations UI, loading states error handling empty states.
**Addresses features:** Complete discover page with all five tracking dimensions.
**Avoids pitfalls:** Pitfall #7 (FTS5 -- already implemented in Phase 1), Pitfall #10 (state conflicts -- per-tab local draft forms).

### Phase 6: Bug Fixes and Polish
**Rationale:** Bug fixes should not block feature delivery. The two critical bugs (thumbnail proxy, download directory dedup) are independent of the tracking feature set and can be implemented at any point.
**Delivers:** Thumbnail proxy endpoint + frontend URL normalization (Pydantic computed field approach), download directory single-source-of-truth fix (get_download_dir helper, remove hardcoded defaults, startup normalization), scan log TTL cleanup, error differentiation (success vs partial vs failed scan status), cross-dimension dedup badges in UI.
**Addresses features:** Thumbnail fixes, download dir dedup, polish.
**Avoids pitfalls:** Pitfall #5 (thumbnail thundering herd -- batch with rate-limit), Pitfall #6 (state mutation -- separate discovered vs downloaded state), Pitfall #12 (unbounded scan log growth), Pitfall #14 (error vs empty differentiation), Pitfall #13 (duplicate DiscoveryResult).

### Phase Ordering Rationale

- **Models first, services second, API third:** Strict dependency chain. No feature code can work without schema in place.
- **Critical infrastructure (rate limiter, WAL mode, FTS5) in Phase 1:** These protect against the highest-impact pitfalls. Building tracking features without them would require rewriting working code later.
- **Single coordinator loop over per-source jobs (Phase 2):** The Architecture research recommends extending the ChannelScanner pattern; the Pitfalls research shows that per-source APScheduler jobs cause thundering herd problems. The single-coordinator design avoids this upfront.
- **Frontend rewrite last:** The DiscoverView must be entirely rewritten. No point building it before APIs are stable and the store layer is ready.
- **Bug fixes parallelizable:** Thumbnail proxy and download directory fixes touch different code paths and can be implemented at any point during the milestone.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (DiscoveryScanner):** The type-dispatch design depends on understanding yt-dlp's extraction patterns for playlists (auto-generated vs manual, unlisted vs private) and trending (region-specific URLs, category browse IDs). The trending extraction path in particular may need a `/gsd-plan-phase --research-phase 2` if yt-dlp's trending support has changed since the codebase was last audited.
- **Phase 5 (Frontend rewrite):** The tab layout, filter panel UX, and results grid component design need UX research to determine the right information density for video cards and the best interaction pattern for batch add/ignore operations. Consider referencing existing ChannelsView.vue patterns and the DiscoverView.vue from v4.0.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Models + Infrastructure):** All patterns are established in the existing codebase: SQLAlchemy model extensions, Alembic migrations, APScheduler configuration, SQLite connection pragmas. Well-documented, no research needed.
- **Phase 3 (API endpoints):** Straightforward CRUD patterns following existing discovery.py router. No research needed.
- **Phase 4 (Store + API client):** Pinia store follows existing taskStore.ts pattern. API client follows existing index.ts pattern. No research needed.
- **Phase 6 (Bug fixes):** Well-understood problems with documented fixes. No research needed.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Verified against official yt-dlp PyPI releases, existing requirements.txt, and codebase analysis. No ambiguity about what's needed. |
| Features | HIGH | All five tracking dimensions verified against existing codebase capabilities (YoutubeService methods, DiscoverySource model, DiscoveryResult model, ChannelScanner pattern). Feature feasibility confirmed by code reading. |
| Architecture | HIGH | Based on thorough codebase analysis of all existing models, API routes, services, and frontend layers. The ChannelScanner pattern is proven and tested. Integration points are clear and well-documented. |
| Pitfalls | HIGH | Verified against yt-dlp GitHub issues, SQLite documentation, APScheduler API reference, Vue/Pinia patterns, and codebase analysis. Pitfalls are grounded in real upstream behavior and project-specific code patterns. |

**Overall confidence:** HIGH

### Gaps to Address

- **Trending feed extraction reliability:** yt-dlp's trending extraction is less reliable than channel/playlist extraction because YouTube frequently changes the trending page structure. The confidence in trending as a feature is HIGH for basic usage but MEDIUM for category-specific trending. Mitigation: implement trending as best-effort with graceful degradation and a stale indicator.
- **FTS5 integration complexity:** Adding FTS5 to an existing SQLAlchemy async setup requires careful trigger management and content sync. The confidence in the approach is HIGH but the implementation complexity is MEDIUM. Mitigation: test FTS5 index sync first, fall back to LIKE with LIMIT for v1 if FTS5 proves too complex.
- **DiscoverySource vs Channel model merge:** The research strongly recommends unifying Channel into DiscoverySource, but this has implications for existing channel scanning code (ChannelScanner reads the Channel model directly). Mitigation: unify at the API surface and UI level first (Phase 1), defer full model merge if it requires too much refactoring of existing channel scanning code. The two systems can coexist temporarily with a mapping layer.

## Sources

### Primary (HIGH confidence)
- Existing codebase analysis: all models, API routes, services, frontend views, stores
- yt-dlp PyPI releases (pypi.org/project/yt-dlp/) -- version pin recommendation
- yt-dlp GitHub documentation -- extractor patterns for search, channel, playlist, trending
- APScheduler documentation -- IntervalTrigger, misfire_grace_time, coalesce, max_instances
- SQLite documentation -- WAL mode, FTS5, EXPLAIN QUERY PLAN

### Secondary (MEDIUM confidence)
- avtdl project (github.com/15532th/avtdl) -- reference for keyword/channel/playlist monitoring architecture
- Apify YouTube Scraper -- reference for standard filter criteria across 40+ countries, 17 categories
- Archive YouTube Content Tracking -- reference for dual keyword+channel tracking with scan intervals
- yt-dlp GitHub issues (#15841, #15949, #16692) -- YouTube extractor breaking change patterns
- spotDL issue #2420 -- rate limiting patterns with yt-dlp

### Tertiary (LOW confidence)
- None -- all findings are verified against official documentation or existing codebase

---
*Research completed: 2026-06-29*
*Ready for roadmap: yes*
