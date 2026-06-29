# You2Bili - 项目路线图

## v5.1 Discover 页面重构与 Bug 修复 (Current, started 2026-06-29)

**核心目标：** 将 discover 页面从旧推荐系统重构为多维度内容跟踪系统（关键词/博主/playlist/热点/主题），支持手动搜索与自动扫描，并修复 YouTube 封面不显示和下载目录重复问题。

**关键架构决策：**
- Models first, services second, API third, frontend last (strict dependency chain)
- 统一 DiscoveryScanner 单协调器替代 per-source APScheduler 作业
- Critical infrastructure (rate limiter, WAL mode, yt-dlp wrapper) in first phase
- 移除 v4.0 评分代码作为第一阶段清理
- Bug fixes 在最后阶段（独立于功能开发）
- 缩略图代理通过 FastAPI streaming endpoint

**Granularity:** Standard (5 phases)
**Coverage:** 18/18 v5.1 requirements mapped

---

### Phases

- [ ] **Phase 7: Infrastructure & Cleanup** — yt-dlp 封装 + 全局限速器 + SQLite WAL 模式 + 索引 + 移除旧评分代码
- [ ] **Phase 8: Tracking Scanner & Core Discovery** — DiscoveryScanner 协调器 + 关键词搜索 + 频道跟踪 + 自动去重 + 扫描历史
- [ ] **Phase 9: Tracking API & Filtering** — 跟踪源筛选条件 API + 保存搜索为跟踪源 + 手动触发扫描 + 缩略图代理
- [ ] **Phase 10: DiscoverView Frontend** — 多标签页 Discover 页面 + 视频卡片网格 + 一键搬运 + 跟踪源管理 UI
- [ ] **Phase 11: Bug Fixes & Polish** — 下载目录去重

---

### Phase Details

### Phase 7: Infrastructure & Cleanup

**Goal:** Backend foundation is stable — yt-dlp consolidated with global rate limiting, SQLite optimized with WAL mode and indexes, all v4.0 scoring code removed from both backend and frontend

**Depends on:** Nothing (first phase of v5.1)

**Requirements:** INFRA-01, INFRA-02, CLEANUP-01, CLEANUP-02

**Success Criteria** (what must be TRUE):
1. All yt-dlp calls go through a centralized `YtDlpWrapper` with shared sliding-window rate limiter, cookie management, and extractor-args configuration
2. SQLite database uses WAL mode with `busy_timeout` at connection setup and has indexes created for all tracking query patterns
3. All v4.0 scoring backend code is removed: `scoring/` directory, `VideoScore` model, `ContentRule` model, `/api/scoring/` route, `/api/rules/` route
4. All v4.0 scoring frontend code is removed: `scoringApi` calls, `rulesApi` calls, old inline API logic in `DiscoverView`
5. All existing tests pass and `npm run build` succeeds after cleanup

**Plans**: TBD

### Phase 8: Tracking Scanner & Core Discovery

**Goal:** Backend can search YouTube videos by keyword, track YouTube channels, auto-scan all tracked sources via a single coordinator loop, deduplicate results, and record scan history

**Depends on:** Phase 7 (requires `YtDlpWrapper` for all yt-dlp calls, DB WAL mode + indexes for query performance)

**Requirements:** TRACK-01, TRACK-02, TRACK-05, SCAN-01, SCAN-02

**Success Criteria** (what must be TRUE):
1. Keyword search via yt-dlp returns YouTube video results with title, URL, view count, duration, publish date, and thumbnail URL
2. Channel/creator tracking extracts the latest videos from a YouTube channel using yt-dlp, returning results in the same format as keyword search
3. `DiscoveryScanner` single-coordinator loop iterates all active `DiscoverySource` items on schedule, dispatching to type-specific yt-dlp extraction methods
4. Videos already downloaded (in the `videos` table) or already discovered (in the `DiscoveryResult` table) are excluded from new scan results
5. Each scan produces a `DiscoveryScanLog` entry with timestamp, discovered count, and status (success/partial/failed)

**Plans**: TBD

### Phase 9: Tracking API & Filtering

**Goal:** Full backend API surface for tracking — per-source filter conditions, save searches as tracked sources, manual scan trigger, thumbnail proxy endpoint

**Depends on:** Phase 8 (requires `DiscoveryScanner` + `DiscoverySource` model + `DiscoveryResult` model to be in place)

**Requirements:** TRACK-03, TRACK-04, SCAN-03, BUG-01

**Success Criteria** (what must be TRUE):
1. Each tracked source supports configurable filter conditions (min/max views, duration range in seconds, publish recency window in days) that the scanner applies during result filtering
2. Users can save a search or search criteria as a new `DiscoverySource` via API, which becomes active in the auto-scan rotation
3. Users can trigger an immediate scan for any tracked source via API, bypassing the scheduled interval
4. YouTube video thumbnails (from `i.ytimg.com`) load correctly in the frontend via a FastAPI streaming proxy endpoint that adds CORS headers

**Plans**: TBD

### Phase 10: DiscoverView Frontend

**Goal:** Users can use the full Discover interface — multi-tab browsing, search with results grid, manage tracked sources, and add videos to the pipeline with one click

**Depends on:** Phase 9 (requires all backend APIs: search, source CRUD, filters, manual scan, thumbnail proxy)

**Requirements:** UI-01, UI-02, UI-03, UI-04

**Success Criteria** (what must be TRUE):
1. Discover page has a multi-tab interface with at least Search, Keywords, and Channels tabs; each tab shows its relevant content type
2. Search results and scan results display as video cards in a responsive grid, each showing thumbnail, title, view count, duration, and publish date
3. Each video card has a one-click "add to pipeline" button that navigates to the task creation page with the video's URL and metadata pre-filled
4. Users can view a list of tracked sources, add new sources, edit existing sources, delete sources, and enable/disable sources from the UI
5. Loading states, empty states, and error states are handled for all views — no blank screens or unhandled errors on API failures

**Plans**: TBD
**UI hint**: yes

### Phase 11: Bug Fixes & Polish

**Goal:** Download directory has a single source of truth — no duplicate `downloads` paths, no hardcoded defaults conflicting with configured paths

**Depends on:** Phase 7 (independent of tracking features; requires clean foundation to make changes safely)

**Requirements:** BUG-02

**Success Criteria** (what must be TRUE):
1. All code references to download directory paths use a single `get_download_dir()` helper or equivalent single source of truth
2. No hardcoded `downloads/` or `./downloads` paths remain in configuration files, models, or services
3. Application startup normalizes or validates the download directory path to prevent creation of duplicate directories

**Plans**: TBD

---

### Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 7. Infrastructure & Cleanup | 0/0 | Not started | - |
| 8. Tracking Scanner & Core Discovery | 0/0 | Not started | - |
| 9. Tracking API & Filtering | 0/0 | Not started | - |
| 10. DiscoverView Frontend | 0/0 | Not started | - |
| 11. Bug Fixes & Polish | 0/0 | Not started | - |

---

## 已归档里程碑

### v5.0 开源化深度改造 — Done ✅ (2026-06-29)

**核心目标：** 把项目从"能跑但混乱的内部工具"改造为"结构清晰、文档完善、便于社区使用和贡献的开源项目"。

**6 phases complete:**
- Phase 1: Repo hygiene & directory structure
- Phase 2: Dead code & redundancy removal
- Phase 3: Configuration system unification
- Phase 4: Backend API normalization
- Phase 5: Frontend cleanup
- Phase 6: Documentation rewrite & build consolidation

### v4.0 智能选题与内容追踪 — Deferred (2026-06-29)

**核心目标：** 从"被动加工"升级为"主动发现"——五维评分 + 智能发现 + 规则引擎 + 内容追踪仪表盘。

**Status:** Deferred. Phase PLANs 已起草但未注册到 ROADMAP，从未执行。
**归档位置:** `.planning/milestones/v4.0-deferred/`

### v3.0 已归档 (2026-06-23) — UX 重设计

### v2.0 已归档 (2026-06-22)

### v1.0 已完成 (Phase 1-3, 2026-06-15)

---

## 已知技术债（carried forward）

- `test_phase10_docs_and_scripts_exist` 路径过时（v2.0 归档后未更新）
- `test_resolve_transcript_text_empty_segments` Phase 8 edge case bug
- 后端 `GET /api/tasks` 缺 `thumbnail_url` 字段（v3.0 DESIGN.md R8 待加）
- `GET /api/onboarding/status` endpoint 未实现
- Frontend bundle 1.19MB，未 code-split（deferred to v6+）

---

*Last updated: 2026-06-29 — v5.1 Discover 页面重构与 Bug 修复 roadmap created (phases 7-11)*
