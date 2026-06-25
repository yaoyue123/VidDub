# Phase 14: 智能发现引擎

**Goal:** 自动发现适合搬运的 YouTube 内容源——频道推荐、趋势抓取、关键词挖掘，自动去重。让用户从"搜什么"变成"看推荐"。

**Dependencies:** Phase 13 (scoring engine)

**Estimated effort:** 4-5 hrs

---

## Architecture

```
┌───────────────────────────────────────────────────┐
│              DiscoveryEngine                        │
│                                                    │
│  ┌────────────┐  ┌──────────┐  ┌───────────────┐ │
│  │ Channel    │  │ Trending │  │ Keyword       │ │
│  │ Recommender│  │ Scraper  │  │ Miner         │ │
│  └─────┬──────┘  └────┬─────┘  └──────┬────────┘ │
│        │              │               │           │
│        ▼              ▼               ▼           │
│  ┌─────────────────────────────────────────────┐  │
│  │         Discovery Pipeline                   │  │
│  │  Fetch → Score → Deduplicate → Rank → Store │  │
│  └─────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────┘
    │
    ▼
  DiscoveryQueue → Frontend "发现" page
```

## Data Model

### New table: `discovery_sources`

```python
class DiscoverySource(Base, TimestampMixin):
    __tablename__ = "discovery_sources"

    id: int (PK)
    type: str              # "channel" | "keyword" | "category" | "trending"
    source_value: str      # channel URL / search keyword / category name
    label: str             # human-readable name
    enabled: bool (default True)
    last_scanned_at: datetime (nullable)
    scan_interval_hours: int (default 24)
    max_results_per_scan: int (default 20)
```

### New table: `discovery_results`

```python
class DiscoveryResult(Base, TimestampMixin):
    __tablename__ = "discovery_results"

    id: int (PK)
    source_id: int (FK → discovery_sources)
    youtube_id: str (indexed)
    title: str
    channel_name: str
    composite_score: float (nullable)  # From scorer
    status: str          # "new" | "scored" | "dubbed" | "ignored"
    discovered_at: datetime
    video_id: int (FK → videos, nullable)  # If already processed
```

## Task Breakdown

### T1: `DiscoverySource` + `DiscoveryResult` models
- File: `backend/app/models/discovery.py`
- Register in `__init__.py`
- **Acceptance:** Tables created

### T2: `ChannelRecommender` — find similar channels
- File: `backend/app/services/scoring/discovery.py`
- Two modes:
  - **Seed-based:** Given channels user already dubs from, find similar via YouTube's `search.list(type=channel, relatedToVideoId=...)`
  - **Category-based:** Search by content category keywords (e.g., "tech reviews 2024")
- Return list of channel suggestions with subscriber count, recent video count
- **Acceptance:** Given a channel URL, returns 5-10 similar channels

### T3: `TrendingScraper` — get trending videos
- Use yt-dlp to scrape YouTube trending by category
- Categories: Tech, Science, Education, Gaming, Music, How-to
- Return top N videos per category with basic metrics
- **Acceptance:** Returns 20 trending videos across 4 categories

### T4: `KeywordMiner` — generate search keywords
- Use SiliconFlow LLM to suggest search keywords based on:
  - User's successful past dubs
  - Current trends
  - Content categories that perform well on Bilibili
- Returns ranked keyword list with rationale
- **Acceptance:** Returns 10-20 suggested search keywords

### T5: `DiscoveryPipeline` — orchestrate discovery
- File: `backend/app/services/scoring/discovery_pipeline.py`
- `run_discovery(source_id)` → fetch videos → score each → deduplicate → store
- Dedup: check against `videos.youtube_id` (already processed) and `discovery_results.youtube_id` (already discovered)
- `run_all_sources()` → run all enabled sources
- APScheduler integration — hourly check for sources due for scan
- **Acceptance:** Pipeline runs end-to-end with a test source

### T6: Discovery API endpoints
- File: `backend/app/api/discovery.py` (extend existing)
- `GET /api/discovery/sources` — list discovery sources
- `POST /api/discovery/sources` — add source
- `DELETE /api/discovery/sources/{id}` — remove source
- `POST /api/discovery/sources/{id}/scan` — trigger scan
- `GET /api/discovery/results` — paginated discovery results (sort by score, filter by status)
- `PUT /api/discovery/results/{id}/ignore` — mark as ignored
- `POST /api/discovery/results/{id}/dub` — create dub task from discovered video
- **Acceptance:** CRUD on sources, results listing with filters

### T7: Unit tests
- File: `backend/tests/unit/test_discovery.py`
- Test dedup logic, channel recommender with mock YouTube API
- **Acceptance:** ≥ 10 tests pass

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/models/discovery.py` | Create | DiscoverySource + DiscoveryResult models |
| `backend/app/services/scoring/discovery.py` | Create | ChannelRecommender, TrendingScraper, KeywordMiner |
| `backend/app/services/scoring/discovery_pipeline.py` | Create | Orchestration + dedup + scheduling |
| `backend/app/api/discovery.py` | Extend | Discovery CRUD + scan triggers |
| `backend/tests/unit/test_discovery.py` | Create | Unit tests |

## Verification

1. **Channel recommender:** Given "Linus Tech Tips" → returns similar tech channels
2. **Trending scraper:** Returns real trending videos from YouTube
3. **Dedup:** Same youtube_id discovered twice → only stored once
4. **Pipeline:** `run_discovery(source_id)` → N new results in DB, all with scores
5. **API:** `POST /api/discovery/results/1/dub` → creates a dub task
