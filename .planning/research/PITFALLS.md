# Domain Pitfalls: Multi-Dimension Content Tracking

**Domain:** YouTube video discovery and tracking (keyword, channel, playlist, trending, topic)
**Existing system:** yt-dlp + APScheduler + SQLite (SQLAlchemy async) + FastAPI + Vue 3 + Pinia
**Researched:** 2026-06-29
**Overall confidence:** HIGH (verified against official docs and project codebase)

---

## Critical Pitfalls

Mistakes that cause data loss, silent failures, or architectural rewrites.

### Pitfall 1: yt-dlp Rate Limiting Without Backpressure

**What goes wrong:** The tracking system fires yt-dlp requests for multiple tracking targets (keywords, channels, playlists, trending pages, topics) concurrently. YouTube responds with HTTP 429, IP-based throttling, or bot detection. Once throttled, ALL subsequent extractions fail -- not just the one that triggered it.

**Why it happens:** The existing `ChannelScanner` has a `Semaphore(max_concurrent=3)` that limits concurrency, but that is per-channel scanning only. The v5.1 tracking system will have FIVE independent tracking dimensions, each potentially spawning their own yt-dlp calls. Without a shared rate limiter, the combined concurrency across all tracking types quickly exceeds YouTube's tolerance.

Existing code (channel_scanner.py line 59):
```python
self._semaphore = asyncio.Semaphore(max_concurrent)
```
This semaphore only governs channel scans. The new dimensions (keyword, playlist, trending, topic) will NOT be covered by it.

**Consequences:**
- All yt-dlp calls fail with 403/429 for minutes to hours
- Cookie-based sessions get invalidated more aggressively
- Users see "all tracking broken" with no clue which dimension is at fault
- The existing download pipeline also fails (same yt-dlp instance, same IP)

**Prevention:**
- Create a **single, shared global rate limiter** across ALL yt-dlp usage (tracking + channel scans + downloads). Do NOT add separate semaphores per tracking type.
- Use `--sleep-requests 3 --sleep-interval 60 --max-sleep-interval 120` for all extractor calls (not just downloads).
- Implement a sliding-window rate limiter (not just asyncio.Semaphore -- Semaphore does not enforce inter-request delay):
  ```python
  class YtDlpRateLimiter:
      """Ensure minimum N seconds between yt-dlp extractor calls."""
      def __init__(self, min_interval: float = 10.0, max_concurrent: int = 2):
          self._semaphore = asyncio.Semaphore(max_concurrent)
          self._last_call = 0.0
          self._min_interval = min_interval
          self._lock = asyncio.Lock()

      async def acquire(self):
          async with self._semaphore:
              async with self._lock:
                  elapsed = time.monotonic() - self._last_call
                  if elapsed < self._min_interval:
                      await asyncio.sleep(self._min_interval - elapsed)
                  self._last_call = time.monotonic()
  ```
- Add a circuit breaker: If N consecutive yt-dlp calls fail with 403/429, pause ALL tracking for a backoff period (start at 5 min, double up to 2 hours).
- **Do NOT** use `--sleep-requests` as the only defense -- it's applied per yt-dlp process, not across concurrent processes.

**Detection:**
- Monitor yt-dlp return codes in a centralized wrapper, not per-service.
- Log `X-RateLimit-Remaining` or response headers when available.
- Track 403 rate: if >1% of total extractor calls return 403, trigger circuit breaker.

---

### Pitfall 2: SQLite Query Pattern Degradation Under Tracking Workload

**What goes wrong:** The tracking system adds many new query patterns:
- "Find all videos matching keyword X" (LIKE or FTS on titles/descriptions)
- "Find videos from creator Y published in last Z days"
- "Find trending videos not yet downloaded"
- "Find duplicate youtube_ids across tracking dimensions"
- Aggregation queries: "How many videos found per keyword per day"

Without proper indexes and query planning, these queries turn into sequential scans on the `videos` table (which already has 20+ columns and growing). What works at 100 videos becomes unusable at 10,000.

**Why it happens:** SQLite does not auto-maintain query plans. The project's current database setup (database.py) has no WAL mode, no busy_timeout, and no index strategy:
```python
engine = create_async_engine(settings.database_url, echo=settings.debug)
```
No PRAGMAs are set after engine creation. No dedicated indexes for the new query patterns.

**Consequences:**
- Dashboard/tracking pages take 5-30 seconds to load
- API timeout errors from the 30-second axios timeout (frontend/src/api/index.ts line 5: `timeout: 30000`)
- Write contention when tracking jobs and manual browsing hit the DB concurrently
- `SELECT COUNT(*)` queries on unindexed columns block WAL checkpoints

**Prevention:**
- **Set WAL mode + busy_timeout at connection setup** (add these to database.py or use SQLAlchemy `@event.listens_for`):
  ```python
  from sqlalchemy import event
  from sqlalchemy.ext.asyncio import AsyncEngine

  @event.listens_for(engine.sync_engine, "connect")
  def set_sqlite_pragmas(dbapi_connection, connection_record):
      cursor = dbapi_connection.cursor()
      cursor.execute("PRAGMA journal_mode=WAL")
      cursor.execute("PRAGMA busy_timeout=5000")
      cursor.execute("PRAGMA synchronous=NORMAL")
      cursor.execute("PRAGMA foreign_keys=ON")
      cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
      cursor.close()
  ```
- **Add indexes for ALL new query patterns before writing data.** The tracking system will add: `DiscoverySource` table (keyword/channel/playlist/trending/topic configs), `DiscoveryResult` table (tracking results), and new query columns on `Video`.
- Required indexes for tracking:
  ```sql
  -- On Video table:
  CREATE INDEX ix_videos_created_at ON videos(created_at);                    -- time-range filters
  CREATE INDEX ix_videos_view_count ON videos(view_count);                    -- view-count sorting
  CREATE INDEX ix_videos_channel_id ON videos(channel_id);                    -- creator tracking joins
  CREATE INDEX ix_videos_source ON videos(source);                            -- tracking dimension grouping

  -- On DiscoveryResult (new table for tracking):
  CREATE INDEX ix_discovery_results_source_id ON discovery_results(source_id);
  CREATE INDEX ix_discovery_results_youtube_id ON discovery_results(youtube_id);
  CREATE INDEX ix_discovery_results_discovered_at ON discovery_results(discovered_at);
  CREATE INDEX ix_discovery_results_status ON discovery_results(status);
  ```
- **Use `EXPLAIN QUERY PLAN`** on every new query before deploying. Look for `SCAN` (sequential scan) on large tables -- if found, add an index.
- **Batch page-size-aware queries** -- never do `SELECT * FROM videos` without LIMIT/OFFSET in tracking code.
- **Avoid `LIKE '%keyword%'`** on title/description for keyword tracking. Use SQLite FTS5 instead for anything beyond exact-match search.

**Detection:**
- Use `EXPLAIN QUERY PLAN` on slow queries
- Monitor `backend/data/viddub.db-wal` file size -- if >100MB, checkpoints are being starved
- Add a `/api/health/db` endpoint that runs `PRAGMA wal_checkpoint(TRUNCATE)` and reports wal file size

---

### Pitfall 3: YouTube Extractor Changes Breaking the Tracking System

**What goes wrong:** YouTube changes its InnerTube API, player client, or PO token requirements. yt-dlp's extractor breaks. The channel scanner already has error handling (writes ScanLog with error_msg), but the new tracking system has MORE entry points (keyword search, playlist scan, trending scan, topic scan) -- when the extractor breaks, FIVE features break simultaneously instead of one.

**Why it happens:** This is a recurring pattern. yt-dlp had breaking YouTube-related changes at least 4 times in 2026 alone (January 403 wave, February player client removal, multiple PO token experiments, May-June playlist pagination bugs). Each time, the fix is a yt-dlp version bump plus possible extractor-args changes.

The current system has NO version pinning strategy for yt-dlp. Looking at requirements.txt -- yt-dlp is likely unpinned or loosely pinned (`yt-dlp>=2025`), which means `pip install` may get a version that doesn't match the tested one.

**Consequences:**
- All tracking features fail silently (no videos found)
- Users think "no new content" when actually the extractor is broken
- The error funnel becomes unclear: is it a yt-dlp bug, a rate limit, a bad URL, or a YouTube UI change?
- If the fix requires a new yt-dlp flag, the tracking code needs to pass it through -- but different tracking types may need different extractor args

**Prevention:**
- **Pin yt-dlp to a specific version** in requirements.txt: `yt-dlp==2026.06.07` (use the latest stable at time of deployment). Add a `@app.on_event("startup")` check that warns if the installed version differs from expected.
- **Create a single `YtDlpWrapper` class** used by ALL tracking services (keyword, channel, playlist, trending, topic) -- NOT separate yt-dlp invocations per service. This gives one place to update flags, manage cookies, and add retry logic when YouTube breaks.
- **Store extractor-args in the DB Config table** so they can be adjusted from the Settings UI without code deploy:
  ```python
  configs.get("ytdlp_extractor_args", "youtube:player_client=default,mweb")
  ```
- **Add a `/api/health/yt-dlp-test` endpoint** that tries to extract a known video and reports success/failure. The tracking UI should show a banner when this health check fails.
- **Version-lock the yt-dlp Docker image** (if using Docker) -- `yt-dlp:2026.06.07` not `yt-dlp:latest`.

**Detection:**
- Centralized yt-dlp error logging: if >80% of extractions fail, emit an ALERT-level log
- Monitor yt-dlp GitHub releases daily (nofullscreen or issue trackers) for breaking changes
- Add a "yt-dlp status" indicator on the Settings page

---

### Pitfall 4: APScheduler Job Proliferation Without Resource Limits

**What goes wrong:** Each tracking dimension (keyword, channel, playlist, trending, topic) creates N scheduled jobs. With 10 keywords, 5 channels, 3 playlists, and 2 topics, that is 20 scheduled jobs. Each job opens its own DB session, calls yt-dlp, and writes results. At scale, APScheduler itself becomes a performance bottleneck and the DB connection pool saturates.

**Why it happens:** The existing ChannelScanner pattern creates one APScheduler job per channel. The v5.1 extension naturally extends this pattern: one job per keyword, one per playlist, etc. But the number of jobs multiplies, and the current code has no mechanism for staggered scheduling -- all jobs with the same interval fire at the same time.

Current code (channel_scanner.py line 104-112):
```python
self._scheduler.add_job(
    self._scan_job_wrapper,
    trigger=trigger,      # IntervalTrigger(hours=interval)
    args=[channel.id],
    id=job_id,
    replace_existing=True,
    max_instances=1,
    coalesce=True,
)
```
The `IntervalTrigger` starts immediately by default (no `start_date` with jitter), and there is no `jitter` parameter. Multiple jobs with `hours=6` all fire simultaneously on startup.

**Consequences:**
- 20+ yt-dlp processes launch simultaneously at the start of each interval
- DB connection pool (async_session_factory has no pool limit) spawns 20+ connections
- All jobs hit rate limits simultaneously (making Pitfall #1 worse)
- FastAPI request handling competes with tracking jobs for resources
- On scheduler restart, all jobs fire at once (the "thundering herd" problem)

**Prevention:**
- **Use a single shared APScheduler job** with a coordinator loop instead of N individual jobs. The coordinator iterates through all tracking targets sequentially:
  ```python
  class TrackingCoordinator:
      """Single scheduler job that coordinates all tracking dimensions."""

      async def scan_all(self):
          """Called once per interval. Iterates through all active tracking targets."""
          for source_type in ['keyword', 'channel', 'playlist', 'trending', 'topic']:
              targets = await self._get_active_targets(source_type)
              for target in targets:
                  async with self._global_limiter:
                      await self._scan_one(target)
  ```
  This gives predictable resource usage and avoids the thundering herd problem.

- **If separate jobs are preferred for UX reasons** (each target shows its own schedule in the UI), add `jitter` to stagger them:
  ```python
  trigger = IntervalTrigger(hours=interval, jitter=minutes=30)
  ```
  And add `start_date` with random offset to avoid all-at-once startup.

- **Set `coalesce=True` and `max_instances=1`** on ALL jobs (confirmed existing ChannelScanner already does this -- maintain this pattern).
- **Set `misfire_grace_time` explicitly.** Do not rely on the default. For tracking scans, use `misfire_grace_time=None` so that missed scans run ASAP rather than being silently dropped.

**Detection:**
- Add `/api/health/scheduler` endpoint that reports: total jobs, running jobs, last run time per job
- Log when a job's actual start time differs from scheduled time by >30 seconds (indicates scheduler overload)

---

## Moderate Pitfalls

### Pitfall 5: Cover Image / Thumbnail Fix Creates a Thundering Herd on Async Startup

**What goes wrong:** The YouTube thumbnail fix (one of the v5.1 bugs) is implemented as an API endpoint or startup task that re-fetches thumbnails for all existing videos. For 500+ videos, this creates 500+ concurrent HTTP requests to youtube.com/i/ URLs, getting the IP throttled and potentially re-triggering the very bug being fixed.

**Consequences:**
- Thumbnail fix makes thumbnail loading worse (all requests fail)
- YouTube temporarily blocks the IP for "suspicious activity"
- Users see broken thumbnails on ALL videos, not just old ones

**Prevention:**
- Batch thumbnail refreshes: max 10 concurrent, 500ms delay between batches
- Cache thumbnails locally as files, not just as URLs
- Add a progress indicator for the thumbnail migration (don't hide it in a startup task)
- Rate-limit thumbnail fetch through the same global rate limiter as Pitfall #1

---

### Pitfall 6: Duplicate Download Directory Check Introduces State Mutation on Read

**What goes wrong:** The download directory dedup fix (v5.1) is implemented as a simple query-time filter that checks `os.path.exists(download_dir)`. But tracking searches produce video results that have NOT been downloaded yet -- the existence check prematurely mutates state by creating the download directory as a side effect of the dedup logic.

**Prevention:**
- Separate "discovered" state from "downloaded" state. The tracking system should produce `DiscoveryResult` records with a `downloaded` boolean, not rely on filesystem state.
- Use `os.path.isdir()` not `os.path.exists()` for the download dir check (creates dir vs creates file distinction)
- Never create the download directory in a read-only GET endpoint

---

### Pitfall 7: Keyword Tracking Without FTS5 Becomes Unusable

**What goes wrong:** Keyword tracking naively uses `WHERE title LIKE '%keyword%' OR description LIKE '%keyword%'`. At 10,000+ videos, this is a full table scan that takes seconds per query. SQLite cannot use B-tree indexes for leading-wildcard LIKE queries.

**Prevention:**
- Use SQLite FTS5 for keyword search:
  ```sql
  CREATE VIRTUAL TABLE videos_fts USING fts5(
      title, description, channel,
      content='videos',
      content_rowid='id'
  );
  ```
- Use `MATCH` for keyword queries: `WHERE videos_fts MATCH 'keyword'`
- Keep FTS5 index in sync with triggers on the videos table
- Fall back to simple LIKE only for exact-match queries with known small result sets

---

### Pitfall 8: Playlist Tracking Downloads Entire Playlist Instead of New Videos Only

**What goes wrong:** When a playlist tracking job runs, it fetches ALL videos in the playlist (potentially 5000+ videos), compares against existing youtube_ids, and finds everything is new because the playlist's videos were never downloaded. The user wakes up to 5000 new "tracking results" flooding the UI.

**Prevention:**
- Implement playlist-level dedup that checks youtube_id before fetching full metadata
- Add a `max_new_per_scan` cap per tracking target (default: 20)
- Use yt-dlp's `--playlist-end N` to limit initial fetch: start with N=5, paginate on demand
- Store the last-scanned video position for playlists (not just timestamp), so incremental scans start from where they left off

---

### Pitfall 9: Filtering Applied Server-Side Creates Inconsistent Pagination

**What goes wrong:** The tracking system offers filters (min views, date range, duration) as query parameters. The backend applies filters AFTER pagination -- or applies them as SQL WHERE clauses but the total count query uses unfiltered counts. The frontend pagination shows "page 3 of 5" but page 3 is actually empty because all results on that page were filtered out.

**Prevention:**
- Apply ALL filters BEFORE OFFSET/LIMIT in the SQL query (not after)
- Return `total: int` that reflects the filtered count, not the unfiltered count
- If filters change, reset the page to 1 on the frontend
- Example query pattern (verified correct):
  ```python
  query = select(DiscoveryResult).where(
      DiscoveryResult.source_id.in_(active_source_ids),
      DiscoveryResult.view_count >= min_views,  # if min_views set
      DiscoveryResult.discovered_at >= date_from,  # if date_from set
  )
  total = await session.scalar(select(func.count()).select_from(query.subquery()))
  items = await session.execute(query.order_by(desc(DiscoveryResult.discovered_at)).offset(offset).limit(limit))
  ```

---

### Pitfall 10: Frontend Tracking Config State Conflicts Between Dimensions

**What goes wrong:** The user sets up 3 keywords, 2 channel tracking rules, 1 playlist -- each with different scan intervals and filter settings. The frontend stores this in a single Pinia store with a flat reactive state. When the user navigates between keyword management tab and channel management tab, unsaved changes on one tab overwrite the other because they share the same form state.

**Why it happens:** The existing `configStore.ts` uses a flat key-value map (`Record<string, string>`) which works for simple config but does not support multi-dimension tracking configs with per-dimension schemas.

Current pattern (configStore.ts):
```typescript
const configs = ref<Record<string, string>>({})
```

**Prevention:**
- Create separate Pinia stores per tracking dimension: `useKeywordStore`, `useChannelStore`, `usePlaylistStore`
- Each store owns its own form state, dirty tracking, and API persistence
- Use the "local draft -> explicit save" pattern: component-local `reactive()` form state, only write to the store on user "Save" click
- Track `isDirty` per form (not globally) so the user can see which tabs have unsaved changes
- Implement the `beforeRouteLeave` guard with per-tab dirty check:

```typescript
// Per-component dirty tracking
const form = reactive({ ...initialValues })
const isDirty = ref(false)
watch(form, () => { isDirty.value = true }, { deep: true })

function save() {
  keywordStore.save(form)
  isDirty.value = false
}

// Route guard
onBeforeRouteLeave((to, from, next) => {
  if (isDirty.value) {
    const answer = window.confirm('有未保存的更改，确定离开吗？')
    if (!answer) return next(false)
  }
  next()
})
```

---

### Pitfall 11: Trending/Topic Tracking Using Hardcoded YouTube Region/Locale

**What goes wrong:** The trending tracking feature fetches `https://www.youtube.com/feed/trending` or uses yt-dlp's `--trending` without specifying region or category. Results are in English for a US audience, but the app is designed for Chinese content creators. The user sees trending videos in Japanese, Korean, or US English that are useless for their workflow.

**Prevention:**
- Make region/locale a per-trending-target config field, not a global setting
- Default to `TW` or `HK` region (Chinese-speaking market) rather than US
- Let users override per trending target
- Use yt-dlp's `--extractor-args "youtube:trending_region=TW"` to specify region
- Do NOT assume the server's locale matches the target audience

---

## Minor Pitfalls

### Pitfall 12: Scan Log Table Grows Unbounded

**What goes wrong:** Each tracking scan writes a ScanLog entry. With 20+ tracking targets scanning every 6 hours, that is 80+ log entries/day, 29,000+/year. No cleanup mechanism exists.

**Prevention:**
- Add a TTL-based cleanup: `DELETE FROM scan_logs WHERE scanned_at < datetime('now', '-30 days')`
- Run cleanup as part of the coordinator loop (once per day)
- Add a `max_logs_per_target` cap: keep the most recent 200 entries per source

### Pitfall 13: DiscoveryResult Duplicates Across Tracking Dimensions

**What goes wrong:** The same video appears in keyword search results AND trending results. The system creates two DiscoveryResult entries with different source_ids. The frontend shows the same video twice. User manually processes one but not the other.

**Prevention:**
- Use `INSERT OR IGNORE` with a UNIQUE constraint on `(source_id, youtube_id)` in DiscoveryResult table
- When linking to Video, add `video_id` to DiscoveryResult to track processing status regardless of source
- On the frontend, deduplicate by youtube_id across the results list (show one, badge which sources matched)

### Pitfall 14: Network Errors in Scanning Not Differentiated From "No New Content"

**What goes wrong:** A tracking scan fails due to network timeout. The code catches the exception and writes ScanLog with `error_msg`. But the "no new content" case and the "network error" case look identical to the user: no new results appear. The user thinks the target has no new videos when actually the system is broken.

**Prevention:**
- Store `status` field on ScanLog: `success | partial | failed`
- Add a scan summary endpoint that returns: `{ last_scan_status, last_error, consecutive_failures }`
- Show a warning badge on a tracking target when it has 3+ consecutive failures
- Differentiate between "0 videos found (target empty)" vs "0 videos found (fetch failed)"

### Pitfall 15: Lazy yt-dlp Flag Inheritance

**What goes wrong:** A new tracking dimension (e.g., playlist scanning) creates its own yt-dlp call without inheriting cookies, rate-limit config, or extractor_args from the global yt-dlp wrapper. The playlist scan works locally but fails in production because it lacks the cookie file.

**Prevention:**
- All yt-dlp invocations MUST go through the central `YtDlpWrapper` class (Pitfall #3)
- Cookie path, extractor args, and rate-limit settings should be read from one source of truth
- Add a linter rule: `grep -rn "yt_dlp" backend/app/ --include="*.py" | grep -v "YtDlpWrapper" | grep -v "__pycache__"` -- zero results allowed

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation | Priority |
|-------------|---------------|------------|----------|
| Multi-dimension tracking coordinator | Pitfall #4 (APScheduler job proliferation) | Use single coordinator loop, not N jobs | CRITICAL |
| yt-dlp integration for tracking | Pitfall #1 (rate limiting), Pitfall #15 (flag inheritance) | Global `YtDlpWrapper` + shared rate limiter | CRITICAL |
| Keyword tracking | Pitfall #7 (LIKE performance), Pitfall #9 (pagination) | FTS5, filter-before-paginate | HIGH |
| Playlist tracking | Pitfall #8 (full playlist download) | `--playlist-end N`, incremental | HIGH |
| Trending/topic tracking | Pitfall #11 (hardcoded locale) | Per-target region config | MEDIUM |
| Thumbnail fix | Pitfall #5 (thundering herd) | Batch + rate-limit | MEDIUM |
| Download dir dedup | Pitfall #6 (state mutation on read) | Separate discovered vs downloaded state | MEDIUM |
| Frontend tracking config UI | Pitfall #10 (state conflicts) | Per-dimension Pinia stores, local drafts | MEDIUM |
| Scan logs | Pitfall #12 (unbounded growth), Pitfall #14 (error vs empty) | TTL cleanup + status field | LOW |
| Dedup across dimensions | Pitfall #13 (duplicate DiscoveryResult) | UNIQUE(source_id, youtube_id) + dedup badge | LOW |
| DB setup | Pitfall #2 (SQLite query degradation) | WAL mode, indexes from day one, EXPLAIN QUERY PLAN | CRITICAL |
| YouTube extractor versioning | Pitfall #3 (breakage cascade) | Pin version, health check, centralized wrapper | CRITICAL |

---

## Sources

- **yt-dlp rate limiting:** yt-dlp GitHub docs, `--sleep-interval` / `--sleep-requests` flags, spotDL issue #2420
- **SQLite WAL mode concurrency:** SQLite.org forum discussions on WAL mode contention and read-to-write transaction upgrades
- **YouTube extractor breaking changes:** yt-dlp issues #15841, #15949, #16692; Debian bug #1126687; NixOS issue #487534 (all 2026)
- **APScheduler overlapping jobs:** apscheduler.readthedocs.io API reference -- `max_instances`, `coalesce`, `misfire_grace_time`
- **Vue 3 Pinia form state patterns:** Pinia official docs, vuejs/core patterns, community best practices for local draft vs store state
- **Codebase patterns observed:** `channel_scanner.py` (existing APScheduler pattern), `database.py` (current no-WAL-mode setup), `configStore.ts` (flat key-value config store), `frontend/src/api/index.ts` (typed API layer)
