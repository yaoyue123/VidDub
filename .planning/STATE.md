---
gsd_state_version: 1.0
milestone: v5.1
milestone_name: Discover 页面重构与 Bug 修复
status: executing
last_updated: "2026-06-29T14:30:00.000Z"
last_activity: 2026-06-29 — Plan 07-04 completed (Remove v4.0 scoring frontend code)
progress:
  total_phases: 11
  completed_phases: 1
  total_plans: 12
  completed_plans: 5
  percent: 42
---

# Project State

## Current Milestone: v5.1 Discover 页面重构与 Bug 修复

Updated: 2026-06-29

---

## Project Reference

**Core Value:** 把"中文观众想看的优质 YouTube 内容"自动搬运到国内平台——下载、翻译、配音、字幕、发布全流程自动化。

**Current Focus:** v5.1 启动 — 将 discover 页面从旧推荐系统重构为多维度内容跟踪系统（关键词/频道），支持手动搜索与自动扫描，并修复 YouTube 封面不显示和下载目录重复问题。

---

## Current Position

Phase: 7 (Infrastructure & Cleanup) — Completed
Plan: 04 (Remove v4.0 scoring frontend code) — Completed
Status: Completed
Last activity: 2026-06-29 — Plan 07-04 completed (Remove v4.0 scoring frontend code)

## v5.1 Roadmap Summary

| Phase | Goal | Reqs | Depends on |
|-------|------|------|------------|
| 7. Infrastructure & Cleanup | yt-dlp wrapper + rate limiter + WAL + indexes + remove old scoring code | INFRA-01, INFRA-02, CLEANUP-01, CLEANUP-02 | — |
| 8. Tracking Scanner & Core Discovery | DiscoveryScanner + keyword search + channel tracking + dedup + scan history | TRACK-01, TRACK-02, TRACK-05, SCAN-01, SCAN-02 | Phase 7 |
| 9. Tracking API & Filtering | Filter conditions + save source + manual trigger + thumbnail proxy | TRACK-03, TRACK-04, SCAN-03, BUG-01 | Phase 8 |
| 10. DiscoverView Frontend | Multi-tab Discover page + video cards + one-click pipeline + source CRUD | UI-01, UI-02, UI-03, UI-04 | Phase 9 |
| 11. Bug Fixes & Polish | Download directory dedup | BUG-02 | Phase 7 |

**Coverage:** 18/18 v5.1 requirements mapped.

---

## Performance Metrics

- Phases completed: 0 / 5
- Plans completed: 4 (07-01, 07-02, 07-03, 07-04)
- Tests passing baseline: pending (will be established in Phase 7)
- Open blockers: 0

---

## Accumulated Context

### v5.1 Key Decisions

- D-v5.1-01: **Single coordinator loop** — Use DiscoveryScanner with single APScheduler coordinator iterating all source types, not per-source jobs
- D-v5.1-02: **Models first, services second, API third, frontend last** — Strict dependency chain for all phases
- D-v5.1-03: **Critical infrastructure first** — YtDlpWrapper, rate limiter, WAL mode in Phase 7 before any feature code
- D-v5.1-04: **Cleanup before building** — Remove v4.0 scoring code in Phase 7 before adding new tracking models
- D-v5.1-05: **Bug fixes last** — Independent of feature work, implemented in Phase 11
- D-v5.1-06: **Thumbnail proxy via FastAPI streaming** — Backend proxying i.ytimg.com through streaming endpoint with CORS headers

### Phase 7 Plan 01 Decisions

- D-INFRA-02-01: **Use engine.sync_engine connect event for PRAGMAs** — register event listener on sync engine (not async) to set WAL/busy_timeout/cache at every connection setup
- D-INFRA-02-02: **Use CREATE INDEX IF NOT EXISTS** — all 8 indexes use IF NOT EXISTS syntax for idempotent re-runs
- D-INFRA-02-03: **Use FTS5 with content-sync triggers** — automatic FTS index sync via AFTER INSERT/DELETE/UPDATE triggers, plus INSERT OR IGNORE for idempotent initial population
- D-INFRA-02-04: **Wire init_db into main.py lifespan** — call `_ensure_indexes()` and `_ensure_fts5()` via `conn.run_sync(init_db)` after `Base.metadata.create_all`

### Phase 7 Plan 02 Decisions

- D-07-02-01: **download_sync kept unchanged** — Downloads need progress hooks and format strings; wrapping through rate limiter deferred to future phase
- D-07-02-02: **Rate limiter skipped in sync path** — extract_info_sync skips rate limiter because sync callers already run with bounded concurrency via their own thread pool; circuit breaker still protects
- D-07-02-03: **CircuitBreaker.call accepts both sync and async callables** — Uses iscoroutinefunction() to dispatch, with fallback to asyncio.to_thread

### Active Todos

- [x] Phase 7, Plan 01: SQLite WAL mode + indexes + FTS5 (INFRA-02) — Done
- [x] Phase 7, Plan 02: YtDlpWrapper with rate limiter (INFRA-01) — Done
- [x] Phase 7, Plan 03: Remove v4.0 scoring backend code (CLEANUP-01)
- [x] Phase 7, Plan 04: Remove v4.0 scoring frontend code (CLEANUP-02)

### Blockers

无

---

## Session Continuity

**Last activity:** 2026-06-29 — Plan 07-04 completed (Phase 7 complete)

**Next steps:**

1. Phase 8: DiscoveryScanner + keyword search + channel tracking
2. Phase 9: Tracking API & Filtering
3. Phase 10: DiscoverView Frontend

---
*Last updated: 2026-06-29 — Phase 7 Plan 04 completed (Remove v4.0 scoring frontend code). Phase 7 complete.*
