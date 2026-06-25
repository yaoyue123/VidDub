# Phase 16: 内容追踪仪表盘

**Goal:** Web 界面展示评分排序的推荐视频列表、频道追踪面板、趋势热榜，支持一键搬运。让用户打开首页就知道"今天搬什么"。

**Dependencies:** Phase 13-15 (scoring + discovery + rules), Phase 12 (UX redesign)

**Estimated effort:** 5-6 hrs

---

## Architecture

```
Frontend Routes:
  / (Dashboard) → 扩展 Hero section 加 "今日推荐"
  /discover (NEW) → 主发现页

┌─────────────────────────────────────────────────────┐
│  /discover — YouTube 智能发现                        │
│                                                     │
│  ┌─ 顶栏 ────────────────────────────────────────┐  │
│  │ [当前规则: 爆款优先 ▼] [扫描源: 全部 ▼] [刷新] │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  ┌─ 推荐视频 grid ───────────────────────────────┐  │
│  │ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐          │  │
│  │ │ 92分 │ │ 88分 │ │ 85分 │ │ 82分 │          │  │
│  │ │ 缩略图│ │ 缩略图│ │ 缩略图│ │ 缩略图│          │  │
│  │ │ 标题  │ │ 标题  │ │ 标题  │ │ 标题  │          │  │
│  │ │ 频道  │ │ 频道  │ │ 频道  │ │ 频道  │          │  │
│  │ │[搬运] │ │[搬运] │ │[搬运] │ │[搬运] │          │  │
│  │ └──────┘ └──────┘ └──────┘ └──────┘          │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  ┌─ 频道追踪 panel (right sidebar) ──────────────┐  │
│  │ 📊 已追踪 12 个频道                             │  │
│  │ Linus Tech Tips  ▸ 3 个新视频  均分 78         │  │
│  │ Veritasium       ▸ 1 个新视频  均分 91         │  │
│  │ [+ 添加频道]                                   │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## Task Breakdown

### T1: Backend — Dashboard aggregation API
- File: `backend/app/api/scoring.py` (extend)
- `GET /api/scoring/dashboard` — returns:
  - Today's top picks (top 10 scored + undiscovered videos)
  - Tracked channel summary (count, avg scores, new videos this week)
  - Recent discovery stats (found/scored/dubbed counts)
  - Current active rule name
- **Acceptance:** Single API call returns all dashboard data

### T2: Backend — Discovery result detail + actions
- File: `backend/app/api/discovery.py` (extend)
- `GET /api/discovery/results/{id}` — detail with full score breakdown
- `POST /api/discovery/results/{id}/dub` — create dub task (already in Phase 14 plan)
- `POST /api/discovery/results/batch-dub` — batch create dub tasks
- `GET /api/discovery/channels` — tracked channel list with stats
- `POST /api/discovery/channels` — add channel to tracking
- `DELETE /api/discovery/channels/{id}` — remove from tracking
- **Acceptance:** Full action set for discovery results

### T3: Frontend — `DiscoverView.vue` (NEW)
- File: `frontend/src/views/DiscoverView.vue`
- Main discover page with three sections:
  1. **Top bar** — rule selector dropdown + source filter + refresh button
  2. **Video card grid** (responsive: 1/2/3/4 columns based on width)
     - Each card: thumbnail, title (truncated 2 lines), channel, composite score badge, "搬运" button
     - Click card → score detail dialog
  3. **Empty state** — "还没有发现视频，添加扫描源或点击刷新"
- Reuse existing components where possible (el-card, el-badge, el-button)
- **Acceptance:** Page renders with mock data, responsive layout

### T4: Frontend — `ScoreDetailDialog.vue` (NEW)
- File: `frontend/src/components/ScoreDetailDialog.vue`
- Modal/drawer showing:
  - Video thumbnail + full title + channel
  - Five-dimension radar chart (use simple CSS bars, no chart library needed)
  - Each dimension: label + score bar + 1-line explanation
  - Raw metrics (views, likes, publish date)
  - Action buttons: [搬运] [忽略] [在 YouTube 打开]
- **Acceptance:** Dialog shows all score dimensions clearly

### T5: Frontend — Dashboard extension
- File: `frontend/src/views/DashboardView.vue` (modify)
- Add "今日推荐" section below hero/checklist
- Show top 5 scored videos as horizontal scrollable cards
- Link to full `/discover` page
- **Acceptance:** Dashboard shows recommendations when available

### T6: Frontend — Navigation update
- File: `frontend/src/layouts/MainLayout.vue` (modify)
- Add "发现" nav item between "首页" and "任务"
- Icon: `Search` or `TrendCharts` from element-plus
- **Acceptance:** Nav shows new "发现" item

### T7: Frontend — Historical leaderboard
- Add "Top Performers" section to `DiscoverView.vue`
- Backend: `GET /api/analytics/top-performers?limit=10` (add to analytics.py)
- Show top 10 historically best-performing dubbed videos (by Bilibili views/likes)
- Card layout: thumbnail, original title, Chinese title, composite score, platform views
- **Acceptance:** Leaderboard shows ranked historical performers

### T8: Frontend — Router
- File: `frontend/src/router/index.ts` (modify)
- Add `/discover` route → `DiscoverView.vue`
- **Acceptance:** Navigating to /discover renders the page

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/api/scoring.py` | Extend | Dashboard aggregation endpoint |
| `backend/app/api/discovery.py` | Extend | Detail + batch actions + channel tracking |
| `backend/app/api/analytics.py` | Extend | top-performers endpoint |
| `frontend/src/views/DiscoverView.vue` | Create | Main discover page + top performers |
| `frontend/src/components/ScoreDetailDialog.vue` | Create | Score detail modal |
| `frontend/src/views/DashboardView.vue` | Modify | Add "今日推荐" section |
| `frontend/src/layouts/MainLayout.vue` | Modify | Add "发现" nav item |
| `frontend/src/router/index.ts` | Modify | Add /discover route |

## Verification

1. **Dashboard API:** Returns top picks + channel summary + stats
2. **Discover page:** Renders video grid with scores, responsive
3. **Score detail:** Dialog shows all 5 dimensions with meaningful explanations
4. **One-click dub:** "搬运" button creates a dub task from discovered video
5. **Nav integration:** "发现" appears in nav, navigates correctly
6. **Empty state:** Shows helpful message when no discoveries yet
7. **Leaderboard:** Top performers section shows historically best-performing dubbed videos
