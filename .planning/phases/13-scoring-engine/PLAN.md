# Phase 13: 选题评分引擎

**Goal:** 实现五维评分模型，对每个 YouTube 视频自动打出 0-100 的综合分，支持批量评分和排序。

**Dependencies:** Phase 12 (UX redesign), existing `channel_scanner.py`, `youtube.py`

**Estimated effort:** 4-6 hrs

---

## Architecture

```
YouTube Data API / yt-dlp
    │
    ▼
┌─────────────────────────────────────────────────┐
│               VideoScorer                        │
│                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │Virality  │ │Translat. │ │Quality   │         │
│  │Scorer    │ │Scorer    │ │Scorer    │         │
│  │ (0-30)   │ │ (0-25)   │ │ (0-20)   │         │
│  └──────────┘ └──────────┘ └──────────┘         │
│  ┌──────────┐ ┌──────────┐                      │
│  │Market    │ │Cost      │                       │
│  │Scorer    │ │Scorer    │                       │
│  │ (0-15)   │ │ (0-10)   │                       │
│  └──────────┘ └──────────┘                      │
│                                                  │
│  → Weighted Sum → Composite Score (0-100)       │
└─────────────────────────────────────────────────┘
    │
    ▼
  VideoScore DB row + sorted recommendations
```

## Data Model

### New table: `video_scores`

```python
class VideoScore(Base, TimestampMixin):
    __tablename__ = "video_scores"

    id: int (PK)
    youtube_id: str (unique, indexed)
    title: str
    channel_name: str
    channel_id: str

    # Five dimensions (0-100 each before weighting)
    virality_score: float       # 传播潜力
    translation_score: float    # 翻译适配度
    quality_score: float        # 内容质量
    market_score: float         # 中文市场潜力
    cost_score: float           # 制作成本

    composite_score: float      # 加权综合分
    weights_used: str (JSON)    # 评分时使用的权重配置

    # Raw data for recalculation
    raw_metrics: str (JSON)     # views, likes, duration, published_at, etc.

    # Scoring metadata
    scored_at: datetime
    scorer_version: str         # e.g., "1.0"
    category: str (nullable)    # LLM-classified content category

    # Links
    video_id: int (FK → videos, nullable)
    thumbnail_url: str (nullable)
```

## Task Breakdown

### T1: `VideoScore` model + migration
- File: `backend/app/models/video_score.py`
- Register in `backend/app/models/__init__.py`
- Auto-create via `Base.metadata.create_all`
- **Acceptance:** `VideoScore` table exists with all columns

### T2: `VideoScorer` service — dimension calculators
- File: `backend/app/services/scoring/scorer.py`
- Five independent scoring functions, each returning 0-100:
  - `_score_virality(metrics)` — view velocity (40%) + engagement rate (30%) + recency boost (20%) + like/dislike ratio (10%)
  - `_score_translation(metrics)` — language density inverse + has_captions bonus + single_speaker bonus + LLM cultural fit assessment
  - `_score_quality(metrics)` — duration sweet spot (5-20min max) + channel authority + title quality
  - `_score_market(metrics)` — category→Bilibili hot zone mapping via lookup table
  - `_score_cost(metrics)` — has_captions + speaker count inverse + requires_editing inverse
- **Acceptance:** Each function takes a dict of raw metrics, returns float 0-100

### T3: `VideoScorer.score_video()` — composite scoring
- Weighted sum: `composite = w1*v + w2*t + w3*q + w4*m + w5*c`
- Default weights: `{virality: 0.30, translation: 0.25, quality: 0.20, market: 0.15, cost: 0.10}`
- Optional custom weights parameter
- Store raw metrics + scores to DB
- **Acceptance:** Input raw video data → output VideoScore with all dimensions

### T4: Content category classifier (SiliconFlow)
- File: `backend/app/services/scoring/classifier.py`
- Function `classify_video_content(title, description, tags) → category`
- Categories: tech, education, entertainment, gaming, music, fitness, news, science, comedy, lifestyle, other
- Uses SiliconFlow Chat API with simple prompt, temperature=0.1
- Cache results per channel (channels usually stay in one category)
- **Acceptance:** Correctly classifies "Linus Tech Tips" → tech, "Veritasium" → science

### T5: `fetch_video_metrics()` — data gathering
- File: `backend/app/services/scoring/metrics.py`
- Try YouTube Data API v3 first (`videos.list(part=statistics,snippet,contentDetails)`)
- Fallback to yt-dlp `--dump-json` for public metadata
- Extract: view_count, like_count, comment_count, published_at, duration, has_captions, category_id, tags
- Rate limiting: max 50 videos/batch via API
- **Acceptance:** Given a youtube_id, returns a metrics dict

### T6: Batch scoring endpoint
- File: `backend/app/api/scoring.py`
- `POST /api/scoring/batch` — accepts list of youtube_ids or channel URL
- Returns scored and sorted list
- `GET /api/scoring/video/{youtube_id}` — get score for single video
- `GET /api/scoring/history` — list recent scores
- **Acceptance:** API returns properly scored results

### T7: Unit tests
- File: `backend/tests/unit/test_scoring.py`
- Test each dimension scorer independently with mock metrics
- Test composite score with different weight configs
- Test edge cases: zero views, missing data, very old videos
- **Acceptance:** ≥ 15 tests pass

## Files to Create

| File | Purpose |
|------|---------|
| `backend/app/models/video_score.py` | VideoScore model |
| `backend/app/services/scoring/__init__.py` | Package init |
| `backend/app/services/scoring/scorer.py` | Five dimension calculators + composite |
| `backend/app/services/scoring/classifier.py` | LLM content classification |
| `backend/app/services/scoring/metrics.py` | YouTube data fetching |
| `backend/app/api/scoring.py` | Scoring API endpoints |
| `backend/app/api/router.py` | Modify | Register scoring router |
| `backend/tests/unit/test_scoring.py` | Unit tests |

## Verification

1. **Unit:** Each scorer function produces correct range (0-100) with known inputs
2. **Integration:** `score_video()` on real YouTube ID returns sensible scores
3. **API:** `POST /api/scoring/batch` with 5 IDs returns 5 scored results sorted by composite
4. **DB:** Scores persist and can be queried by youtube_id
