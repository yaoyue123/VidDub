# Feature Landscape: Multi-Dimension Content Tracking

**Domain:** YouTube content discovery and tracking for cross-platform repurposing
**Researched:** 2026-06-29
**Research question:** How do multi-dimension content tracking systems work, what are expected behaviors for each tracking dimension, and what filtering capabilities are table stakes vs differentiators?

---

## Context: Existing Infrastructure

This feature set builds on top of existing assets already present in the codebase:

- **`DiscoverySource` model** -- supports `channel | keyword | category | trending` types with `source_value`, `label`, `scan_interval_hours`, `max_results_per_scan`, `last_scanned_at`
- **`DiscoveryResult` model** -- stores discovered videos linked to a source with `youtube_id`, `title`, `channel_name`, `composite_score`, `status` (new/scored/dubbed/ignored)
- **`ContentRule` model** -- scoring weights, filter conditions (JSON), whitelist/blacklist channels and keywords
- **`Channel` model** -- dedicated channel tracking with `filter_min_views`, `filter_min_duration_sec`, `filter_max_duration_sec`, `scan_interval_hours`, and APScheduler integration
- **`ChannelScanner`** -- APScheduler-driven periodic scanner with `_apply_filters`, `_bulk_add_videos` (dedup + auto-create download task), `ScanLog` recording
- **`YoutubeService`** -- `search_sync`, `get_channel_videos_sync`, `get_video_info_sync` wrapping yt-dlp
- **`VideoScore` model** -- 5-dimension scoring (virality, translation, quality, market, cost) plus `raw_metrics` JSON
- **`DiscoverView.vue`** -- existing page showing scored video grid with sidebar for tracked channels

**Key architectural fact:** The project has NO access to YouTube Data API v3 (no API key). All discovery uses yt-dlp's extractor, which returns flat metadata without engagement velocity data or trending feeds.

---

## Five Tracking Dimensions

### 1. Keyword Tracking

**How it works:** User enters search terms. System periodically executes `ytsearch:N:query` via yt-dlp, normalizes results, deduplicates against existing videos.

**Expected behaviors:**
| Behavior | Table Stake / Differentiator | Complexity | Notes |
|----------|------------------------------|------------|-------|
| Add/remove tracked keywords in UI | Table stake | Low | CRUD on DiscoverySource with type=keyword |
| Manual search with instant results | Table stake | Low | Already exists via `POST /discovery/search` |
| Periodic auto-scan (configurable interval) | Table stake | Medium | Reuse ChannelScanner pattern for keyword sources |
| Dedup against already-seen + already-downloaded videos | Table stake | Medium | Check DiscoveryResult + Video tables |
| View results as filterable grid | Table stake | Medium | Existing DiscoverView needs refactoring |
| Per-keyword filter conditions (min views, duration range) | Differentiator | Medium | Extend Channel's filter pattern to DiscoverySource |
| Keyword grouping / tagging ("tech keywords", "edu keywords") | Differentiator | High | Adds group model, group-based scanning |
| Bulk keyword import (CSV, one-per-line) | Differentiator | Low | Simple textarea with line parsing |

**Typical implementation pattern:** Keyword sources are stored in `discovery_sources` with `type=keyword`. A `KeywordScanner` (or extended `ChannelScanner`) iterates enabled keyword sources, calls `YoutubeService.search()` for each, applies per-source filters, deduplicates via `youtube_id`, and writes results to `discovery_results`. APScheduler triggers on configurable intervals.

**yt-dlp behavior note:** `ytsearch` returns results sorted by YouTube's relevance algorithm. There is no way to get keyword-specific trending or recency-sorted results through yt-dlp's search mode. For recency-sorted keyword results, batch scanning with date comparison is the only option.

---

### 2. Creator / Channel Tracking

**How it works:** User adds a YouTube channel URL. System periodically scans the channel's uploads, filters by criteria, notifies of new videos.

**Expected behaviors:**
| Behavior | Table Stake / Differentiator | Complexity | Notes |
|----------|------------------------------|------------|-------|
| Add/remove tracked channels | Table stake | Low | Existing `POST /api/channels` + CRUD |
| Periodic auto-scan with configurable interval | Table stake | Medium | Existing `ChannelScanner` pattern |
| Per-channel filter conditions (min views, duration) | Table stake | Medium | Already exists in Channel model |
| Last-scanned timestamp, scan history | Table stake | Medium | Existing `ScanLog` model |
| One-click scan-now | Table stake | Low | Existing `POST /channels/{id}/scan-now` |
| View channel stats (sub count, video count) | Differentiator | Medium | Requires full metadata extraction per channel, not just flat scan |
| Channel RSS fallback (no full extract) | Differentiator | Medium | Some channels block yt-dlp; RSS feed is lighter weight |
| Channel health/activity indicators (last upload, posting frequency) | Differentiator | Medium | Compare scan dates, compute upload frequency from metadata |
| Auto-disable channels that error repeatedly | Differentiator | Low | Count consecutive scan errors, auto-disable at threshold (e.g. 5) |

**Existing state:** Channel tracking is already well-implemented. The `Channel` model, `ChannelScanner`, scan history, per-channel filters, and APScheduler integration all exist. The gap is that channel concept is separate from the "discovery source" concept -- they should be unified in the UI.

**Key design decision:** Should `Channel` remain a separate model or be merged into `DiscoverySource` with `type=channel`? Recommendation: Unify under `DiscoverySource` for consistent API surface. The `Channel` model has richer fields (filters, auto_publish). Migrate filter fields into `DiscoverySource` as optional JSON or dedicated columns.

---

### 3. Playlist Tracking

**How it works:** User provides a YouTube playlist URL. System periodically flattens the playlist, checks for new entries, and treats each entry as a discovered video.

**Expected behaviors:**
| Behavior | Table Stake / Differentiator | Complexity | Notes |
|----------|------------------------------|------------|-------|
| Add/remove tracked playlists | Table stake | Low | CRUD on DiscoverySource with type=playlist |
| Periodic flatten-and-compare | Table stake | Medium | yt-dlp supports playlist extraction natively |
| Track playlist metadata (title, item count, last updated) | Table stake | Low | Extract from yt-dlp playlist result metadata |
| Order-preserving result display | Table stake | Low | Playlist has inherent ordering; preserve it in results |
| Cross-playlist dedup (same video in multiple playlists) | Differentiator | Medium | Use existing youtube_id dedup, but flag which playlists it appeared in |
| Notify on playlist-level changes (items removed, reordered) | Differentiator | High | Requires storing playlist snapshot and diffing |
| Auto-create task for all new playlist items | Differentiator | Medium | `auto_create_dub` flag on source |

**yt-dlp capability:** yt-dlp natively handles playlist URLs. `ydl.extract_info(playlist_url)` returns `entries` list, playlist metadata (`title`, `channel`, `webpage_url`, `playlist_count`). Use `extract_flat="in_playlist"` for performance (same as channel scanning).

**Distinction from channel tracking:** Playlists can cross channels (e.g., "Best of 2024" curated list), can be user-curated (not just channel uploads), and have different update patterns (less frequent, batch nature).

---

### 4. Trending Tracking

**How it works:** System fetches YouTube trending/explore page for specific regions/categories. Extracts currently trending videos.

**Expected behaviors:**
| Behavior | Table Stake / Differentiator | Complexity | Notes |
|----------|------------------------------|------------|-------|
| Track trending by region/country | Table stake | Medium | yt-dlp supports `--trending` via specific URLs |
| Track trending by category (Music, Gaming, News, etc.) | Differentiator | Medium | YouTube categories map to specific trending pages |
| Periodic trending snapshot | Table stake | Low | Same scan interval pattern, shorter intervals recommended (4h) |
| Trending score (position on trending list) | Differentiator | Low | Store rank position in DiscoveryResult metadata |
| Track trending history (was this video trending yesterday?) | Differentiator | Medium | Requires result history, not just latest snapshot |
| Trending vs viral detection (velocity spike) | Anti-feature | High | Not possible without YouTube Data API view velocity data |

**yt-dlp trending access:** yt-dlp can extract YouTube trending via URL patterns. The main approach is `ytsearch:trending` or extracting the YouTube explore/trending page. However, yt-dlp's trending support is less reliable than channel/playlist extraction because YouTube frequently changes the trending page structure.

**Known limitation:** Trending data from yt-dlp is less structured than from YouTube Data API. Category-specific trending may require parsing the YouTube explore page, which is fragile. Recommend making trending tracking best-effort with graceful degradation.

---

### 5. Topic Tracking

**How it works:** User defines a topic (e.g., "machine learning", "cooking recipes"). System combines keyword search, AI content classification, and channel suggestions to find relevant videos across multiple sources.

**Expected behaviors:**
| Behavior | Table Stake / Differentiator | Complexity | Notes |
|----------|------------------------------|------------|-------|
| Topic definition with descriptive label | Table stake | Low | CRUD on DiscoverySource with type=topic |
| Multi-keyword expansion (topic -> set of search queries) | Differentiator | High | Use AI to generate related search terms |
| Cross-source aggregation (same topic across channels + keywords) | Differentiator | Medium | Results from multiple sources tagged with topic ID |
| Content category matching (auto-classify video by content type) | Differentiator | Medium | LLM classification of video title + description |
| Topic-specific filter presets ("only videos < 20min for quick dubs") | Differentiator | Low | Store filter conditions per topic source |
| AI-powered content relevance scoring for topic | Anti-feature | High | This is v4.0 scoring engine territory -- deferred |

**Design note:** Topic tracking is the most complex dimension. It combines elements of keyword tracking (search terms), channel tracking (suggested channels), and content classification. For v5.1, keep topic tracking simple: a topic is a label + one or more associated search keywords. Defer AI expansion and cross-source aggregation.

---

## Filtering Capabilities

### Table Stakes Filters

Filters every tracking system must have. Missing these makes the product feel incomplete.

| Filter | Applicable Dimensions | yt-dlp Availability | Implementation |
|--------|----------------------|-------------------|----------------|
| **Min view count** | All | View count in flat extract | Post-filter after yt-dlp result return |
| **Max duration** | All | Duration in flat extract | Post-filter |
| **Min duration** | All | Duration in flat extract | Post-filter |
| **Publish date range** | Keyword, Playlist | Not in flat extract; requires `--date` for search | For keywords, pass `--date` / `--dateafter` to yt-dlp; for others, post-filter on upload_date |
| **Sort order** (relevance, date, views, rating) | Keyword, Trending | yt-dlp sort: relevance only | Keyword: ytsearch uses relevance; no sort parameter available |
| **Content type** (video, Short, live) | All | Available in flat extract | Post-filter on `duration` (Shorts < 60s) and `live_status` |

**Reality check:** yt-dlp's search (`ytsearch`) does NOT support Google-quality filters. There is no `order=date` or `publishedAfter=` parameter. All filtering beyond keyword matching is done post-fetch. This is a fundamental limitation vs YouTube Data API v3.

### Differentiator Filters

Features that add real value but are not universally expected.

| Filter | Value | Complexity | yt-dlp Viability |
|--------|-------|------------|------------------|
| **Language filter** (English only, Chinese only, etc.) | Avoid non-English content | Medium | `--extractor-args "youtube:lang=en"` or post-filter on `original_url`/channel metadata |
| **Channel upload frequency** ("channels posting >1/week") | Find active channels | Low | Computed from scan history |
| **Engagement rate** (likes/views ratio) | Identify high-quality content | Low | `like_count / view_count`, post-filter |
| **Category/niche filter** (tech, education, entertainment) | Narrow to profitable niches | Medium | LLM classify from title+description, or yt-dlp category field |
| **Has captions** (video has auto-generated subtitles) | Reduce translation cost | Low | Check `subtitles` field from yt-dlp full extraction |
| **Blacklist keywords** (exclude videos with X in title/channel) | Block undesirable content | Low | Post-filter string matching |
| **Whitelist channels** (only show videos from these channels) | Trusted creators only | Low | Post-filter on channel URL/channel ID |
| **Min comment count** | Gauge engagement depth | Low | Post-filter |
| **Freshness relative to known seen** ("only videos since last scan") | Avoid re-scanning old content | Low | Compare `upload_date` with `last_scanned_at` |
| **Exclude already-dubbed** | Avoid rework | Low | Cross-reference DiscoveryResult.status + Video table |

---

## Anti-Features

Features that look valuable but should be explicitly avoided in v5.1.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **View velocity detection** ("10K views/hour") | Requires YouTube Data API v3 polling at <1h intervals; yt-dlp gives only total view count at snapshot time | Use view count as-is or ignore; accept the limitation |
| **AI-powered content relevance scoring** | This was v4.0 deferred. LLM classification per video adds cost and latency for uncertain value | Simple keyword/title matching; defer to later milestone |
| **Trending real-time feed** | YouTube trending page structure changes frequently; yt-dlp extraction is fragile | Scheduled trending snapshots (every 4h) with stale indicator |
| **Multi-user tracking workspaces** | Single-user tool; adds auth, isolation, and UI complexity | Label-based tagging for organizational purposes only |
| **Social listening / cross-platform trend analysis** | Scope creep; the pipeline is YouTube-to-Bilibili | Stay focused on YouTube content discovery |
| **Predictive "will this go viral in China?"** | Requires training data from previous dubs + Bilibili analytics | Simple scored filters (views + engagement rate) are sufficient |
| **Automated channel suggestion** ("you might also like") | Requires graph analysis or recommendation algorithms | Manual find-and-add is adequate for single-user tool |

---

## Feature Dependencies

### Data Flow
```
Tracking Source (DiscoverySource)
    |
    v
Scanner (APScheduler job)
    |
    v
yt-dlp extraction (search / channel / playlist / trending)
    |
    v
Apply per-source filters (views, duration, language, etc.)
    |
    v
Deduplicate against existing DiscoveryResult + Video records
    |
    v
Write new DiscoveryResult records
    |
    v
Frontend polling / user notification
    |
    v
User reviews results -> "Add to pipeline" -> Create Video + Download Task
```

### Dependency Graph
```
Feature                        Depends On
------                         ----------
DiscoverySource CRUD           Existing DiscoverySource model
Keyword scanning               YoutubeService.search()
Channel scanning               Existing ChannelScanner (reuse/extend)
Playlist scanning              yt-dlp playlist extraction
Trending scanning              yt-dlp trending page extraction
Topic tracking                 Keyword scanning + multi-query support
Per-source filter config       Extend DiscoverySource with filter_* columns
Scan interval management       Existing APScheduler integration
Scan history (ScanLog)         Existing ScanLog model (extend for all source types)
Dedup pipeline                 Existing _bulk_add_videos logic (generalize)
Results grid UI                Existing DiscoverView.vue (refactor)
One-click add to pipeline      Existing discoveryApi.dub() + discoveryApi.add()
```

### Phase Ordering Within Milestone
```
Phase A: DiscoverySource unification (merge Channel into DiscoverySource, add playlist/trending types)
Phase B: Scanner generalization (extend ChannelScanner to KeywordScanner / PlaylistScanner / TrendingScanner)
Phase C: New dimension scanners (keyword, playlist, trending, topic implementations)
Phase D: Frontend refactor (DiscoverView -> multi-tab per dimension, source management UI)
Phase E: Filter expansion (add more per-source filter options to DiscoverySource)
Phase F: Polish + dedup + edge cases
```

---

## Behavioral Expectations by Dimension

### Keyword: Expected User Workflow
1. User types a keyword in search bar -> instant results appear (existing behavior)
2. User clicks "Save keyword" -> keyword added as DiscoverySource with type=keyword
3. System auto-scans saved keywords on schedule -> new results appear in "Discovery Results" tab
4. User can set per-keyword filters: min_views, duration, publish window
5. Results show which keyword matched (important when multiple keywords are tracked)

### Channel: Expected User Workflow
1. User pastes a channel URL -> channel info fetched, basic stats shown
2. User sets scan interval (default 6h), filters
3. Auto-scan runs -> new videos auto-discovered with source="channel"
4. User sees "3 new videos since last scan" indicator
5. One-click "dub all new" or individual selection

### Playlist: Expected User Workflow
1. User pastes a playlist URL -> playlist title + item count fetched
2. Auto-scan flattens playlist -> compares against last snapshot -> shows new items
3. User sees playlist metadata (curator, total items, last updated)
4. Results show playlist order preserved
5. Same video appearing in multiple playlists is deduplicated but cross-referenced

### Trending: Expected User Workflow
1. User selects region (default: Global/US) and optionally category
2. System fetches current trending list -> shows ranked results
3. Trending badge shows position (#3 trending in US/Music)
4. Auto-refresh at shorter interval (4h)
5. User can filter trending by: min views, category, content type
6. **Stale indicator:** "Trending 6h ago" vs "Trending 1h ago"

### Topic: Expected User Workflow
1. User creates "Machine Learning" topic with keywords: [ML, deep learning, neural networks, AI research]
2. System runs all associated keywords as batch scan
3. Results are tagged with topic label, deduplicated across keyword variants
4. User sees aggregated results under the topic tab
5. Topic filters apply to all associated keywords uniformly

---

## Complexity Assessment

| Dimension | Backend Complexity | Frontend Complexity | Total | Key Risk |
|-----------|-------------------|--------------------|-------|----------|
| Keyword | Medium | Low | **Medium** | yt-dlp search limitations |
| Channel | Low (exists) | Low (exists) | **Low** | Minimal new work needed |
| Playlist | Low-Medium | Low | **Low-Medium** | Edge cases with private/deleted playlists |
| Trending | Medium | Low | **Medium** | yt-dlp trending reliability |
| Topic | High | Medium | **High** | Aggregation across sources |

---

## Sources

- **yt-dlp documentation** (github.com/yt-dlp/yt-dlp): extractor patterns for search, channel, playlist, trending -- HIGH confidence (verified via codebase usage)
- **Existing codebase analysis**: `DiscoverySource`, `DiscoveryResult`, `ChannelScanner`, `YoutubeService`, `DiscoverView.vue` -- HIGH confidence (direct code reading)
- **avtdl project** (github.com/15532th/avtdl): reference for keyword/channel/playlist monitoring architecture with Monitor -> Filter -> Action pipeline -- MEDIUM confidence (codebase analysis via web docs)
- **Apify YouTube Scraper** (apify.com/solidcode/youtube-scraper): reference for standard filter criteria across 40+ countries, 17 categories -- MEDIUM confidence (product docs)
- **Archive YouTube Content Tracking** (help.archive.com): reference for dual keyword+channel tracking with 4h/12h scan intervals -- MEDIUM confidence (product docs)
- **v4.0 deferred plans** (`milestones/v4.0-deferred/`): previous scoping for scoring engine, discovery engine, rule engine -- HIGH confidence (project-internal docs)
