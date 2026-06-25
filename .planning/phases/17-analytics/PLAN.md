# Phase 17: 数据分析与优化

**Goal:** 追踪已搬运视频在国内平台的表现，对比预测评分与实际效果，形成评分模型反馈闭环。让评分越来越准。

**Dependencies:** Phase 13-16

**Estimated effort:** 3-4 hrs

---

## Architecture

```
预测评分 (Phase 13)          实际表现 (Bilibili API / 手动录入)
        │                              │
        ▼                              ▼
┌──────────────────────────────────────────────────┐
│              PerformanceTracker                   │
│                                                  │
│  ┌─────────────────┐   ┌──────────────────┐     │
│  │ Score vs Reality │   │ Monthly Report   │     │
│  │ Comparator       │   │ Generator        │     │
│  └────────┬────────┘   └────────┬─────────┘     │
│           │                     │                │
│           ▼                     ▼                │
│  ┌──────────────────────────────────────────┐   │
│  │         Analytics DB (performance_logs)    │   │
│  │  video_id | platform | views | likes |    │   │
│  │  comments | shares | predicted_score |    │   │
│  │  score_accuracy | logged_at               │   │
│  └──────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

## Data Model

### New table: `performance_logs`

```python
class PerformanceLog(Base, TimestampMixin):
    __tablename__ = "performance_logs"

    id: int (PK)
    video_id: int (FK → videos, indexed)
    youtube_id: str (indexed)

    # Platform performance
    platform: str           # "bilibili" | "ixigua"
    platform_views: int
    platform_likes: int
    platform_comments: int
    platform_shares: int (nullable)
    platform_url: str (nullable)

    # Comparison
    predicted_score: float   # What we predicted
    actual_score: float      # Normalized 0-100 based on actual performance
    score_accuracy: float    # |predicted - actual| (lower = more accurate)

    # Metadata
    logged_at: datetime
    fetch_method: str       # "api" | "manual" | "estimated"
```

## Task Breakdown

### T1: `PerformanceLog` model
- File: `backend/app/models/performance_log.py`
- Register in `__init__.py`
- **Acceptance:** Table created

### T2: `PerformanceTracker` service
- File: `backend/app/services/scoring/performance.py`
- `log_performance(video_id, platform, metrics)` — record actual performance
- `calculate_actual_score(platform_views, platform_likes, platform_comments) → float`
  - Normalize platform metrics to 0-100 scale
  - Bilibili: weighted by views + coins + favorites + danmu count
  - Xigua: weighted by views + likes + comments
- `compare_predicted_vs_actual(youtube_id) → dict`
  - Returns predicted_score, actual_score, accuracy, trend
- `get_score_accuracy_stats(days=30) → dict`
  - Average accuracy, prediction bias (over/under estimate), accuracy trend
- **Acceptance:** Track and compare scores

### T3: Performance API endpoints
- File: `backend/app/api/analytics.py` (NEW)
- `POST /api/analytics/performance` — log performance data
- `GET /api/analytics/performance/{video_id}` — get performance for a video
- `GET /api/analytics/score-accuracy` — overall scoring accuracy stats
- `GET /api/analytics/monthly-report?year=2026&month=6` — monthly summary
- **Acceptance:** CRUD on performance logs + stats endpoint

### T4: Monthly report generator
- File: `backend/app/services/scoring/report.py`
- `generate_monthly_report(month) → dict`
  - Summary: total videos dubbed, total views across platforms, avg score
  - Top performers: best 5 videos by actual performance
  - Score accuracy: predicted vs actual correlation
  - Recommendations: suggested weight adjustments
- Output as structured JSON (frontend renders)
- **Acceptance:** Report generates with all sections

### T5: Silent auto-logging hook
- File: `backend/app/services/scoring/performance.py` (extend)
- After publish completes (Phase 7), wait 48h then try to fetch platform stats
- For Bilibili: try API or estimate from publish record metadata
- For Xigua: try API or mark as `fetch_method="manual"`
- Non-blocking — failure just means user manually logs later
- **Acceptance:** Publish → auto-schedules delayed performance fetch

### T6: Unit tests
- File: `backend/tests/unit/test_performance.py`
- Test score normalization, accuracy calculation
- **Acceptance:** ≥ 8 tests pass

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/models/performance_log.py` | Create | PerformanceLog model |
| `backend/app/services/scoring/performance.py` | Create | Tracker + auto-logging |
| `backend/app/services/scoring/report.py` | Create | Monthly report generator |
| `backend/app/api/analytics.py` | Create | Analytics API endpoints |
| `backend/app/services/scheduler.py` | Modify | Hook into publish completion |
| `backend/app/api/router.py` | Modify | Register analytics router |
| `backend/tests/unit/test_performance.py` | Create | Unit tests |

## Verification

1. **Log performance:** `POST /api/analytics/performance` with metrics → stored in DB
2. **Compare:** `GET /api/analytics/performance/{id}` → predicted vs actual shown
3. **Accuracy stats:** `GET /api/analytics/score-accuracy` → mean error + bias
4. **Monthly report:** `GET /api/analytics/monthly-report?month=6` → full report JSON
5. **Auto-log:** After publish → 48h later → attempt performance fetch
