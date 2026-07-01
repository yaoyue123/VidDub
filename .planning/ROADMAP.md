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

- [x] **Phase 7: Infrastructure & Cleanup** — yt-dlp 封装 + 全局限速器 + SQLite WAL 模式 + 索引 + 移除旧评分代码
- [x] **Phase 8: Tracking Scanner & Core Discovery** — DiscoveryScanner 协调器 + 关键词搜索 + 频道跟踪 + 自动去重 + 扫描历史 (2/2 plans done)
- [x] **Phase 9: Tracking API & Filtering** — 跟踪源筛选条件 API + 保存搜索为跟踪源 + 手动触发扫描 + 缩略图代理 (2/2 plans done)
- [x] **Phase 10: DiscoverView Frontend** — 多标签页 Discover 页面 + 视频卡片网格 + 一键搬运 + 跟踪源管理 UI (3/3 plans done)
- [x] **Phase 11: Bug Fixes & Polish** — 下载目录去重 (1/1 plans done)

---

### Phase Details

### Phase 7: Infrastructure & Cleanup

**Goal:** Backend foundation is stable — yt-dlp consolidated with global rate limiting, SQLite optimized with WAL mode and indexes, all v4.0 scoring code removed from both backend and frontend

**Depends on:** Nothing (first phase of v5.1)

**Requirements:** INFRA-01, INFRA-02, CLEANUP-01, CLEANUP-02

**Progress:** 4/4 plans complete

**Success Criteria** (what must be TRUE):
1. All yt-dlp calls go through a centralized `YtDlpWrapper` with shared sliding-window rate limiter, cookie management, and extractor-args configuration
2. SQLite database uses WAL mode with `busy_timeout` at connection setup and has indexes created for all tracking query patterns
3. All v4.0 scoring backend code is removed: `scoring/` directory, `VideoScore` model, `ContentRule` model, `/api/scoring/` route, `/api/rules/` route
4. All v4.0 scoring frontend code is removed: `scoringApi` calls, `rulesApi` calls, old inline API logic in `DiscoverView`
5. All existing tests pass and `npm run build` succeeds after cleanup

**Plans**: 4 plans

```
Plans:
- [x] 07-01-PLAN.md — SQLite WAL mode + busy_timeout + indexes + FTS5 (INFRA-02)
- [x] 07-02-PLAN.md — YtDlpWrapper with rate limiter + circuit breaker + wiring (INFRA-01)
- [x] 07-03-PLAN.md — Remove v4.0 scoring backend code (CLEANUP-01)
- [x] 07-04-PLAN.md — Remove v4.0 scoring frontend code (CLEANUP-02)
```

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

**Plans**: 2 plans

```
Plans:
- [x] 08-01-PLAN.md — Extend DiscoverySource/DiscoveryResult models + DiscoveryScanLog (TRACK-01, TRACK-02, SCAN-02)
- [x] 08-02-PLAN.md — DiscoveryScanner coordinator loop + dedup + scan logs + lifecycle wiring (SCAN-01, TRACK-05, SCAN-02)
```

### Phase 9: Tracking API & Filtering

**Goal:** Full backend API surface for tracking — per-source filter conditions, save searches as tracked sources, manual scan trigger, thumbnail proxy endpoint

**Depends on:** Phase 8 (requires `DiscoveryScanner` + `DiscoverySource` model + `DiscoveryResult` model to be in place)

**Requirements:** TRACK-03, TRACK-04, SCAN-03, BUG-01

**Success Criteria** (what must be TRUE):
1. Each tracked source supports configurable filter conditions (min/max views, duration range in seconds, publish recency window in days) that the scanner applies during result filtering
2. Users can save a search or search criteria as a new `DiscoverySource` via API, which becomes active in the auto-scan rotation
3. Users can trigger an immediate scan for any tracked source via API, bypassing the scheduled interval
4. YouTube video thumbnails (from `i.ytimg.com`) load correctly in the frontend via a FastAPI streaming proxy endpoint that adds CORS headers

**Status:** Complete (2/2 plans done)
**Plans**: 2 plans

```
Plans:
- [x] 09-01-PLAN.md — Extend source CRUD with filter fields + save-search-as-source (TRACK-03, TRACK-04)
- [x] 09-02-PLAN.md — Wire manual scan to DiscoveryScanner + thumbnail proxy endpoint (SCAN-03, BUG-01)
```

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

**Plans**: 3 plans
**UI hint**: yes

```
Plans:
- [x] 10-01-PLAN.md — API client extension + discoveryStore Pinia store (UI-01, UI-02, UI-03, UI-04)
- [x] 10-02-PLAN.md — VideoCard reusable component (UI-02, UI-03)
- [x] 10-03-PLAN.md — DiscoverView multi-tab rewrite with Search/Keywords/Channels tabs (UI-01, UI-02, UI-03, UI-04)
```

### Phase 11: Bug Fixes & Polish

**Goal:** Download directory has a single source of truth — no duplicate `downloads` paths, no hardcoded defaults conflicting with configured paths

**Depends on:** Phase 7 (independent of tracking features; requires clean foundation to make changes safely)

**Requirements:** BUG-02

**Success Criteria** (what must be TRUE):
1. All code references to download directory paths use a single `get_download_dir()` helper or equivalent single source of truth
2. No hardcoded `downloads/` or `./downloads` paths remain in configuration files, models, or services
3. Application startup normalizes or validates the download directory path to prevent creation of duplicate directories

**Plans**: 1 plan

```
Plans:
- [x] 11-01-PLAN.md — Single get_download_dir() helper to eliminate duplicate directory paths (BUG-02)
```

---

### Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 7. Infrastructure & Cleanup | 4/4 | Complete | 2026-06-29 |
| 8. Tracking Scanner & Core Discovery | 2/2 | Complete | 2026-06-29 |
| 9. Tracking API & Filtering | 2/2 | Complete | 2026-06-29 |
| 10. DiscoverView Frontend | 3/3 | Complete | 2026-06-29 |
| 11. Bug Fixes & Polish | 1/1 | Complete | 2026-06-29 |

---

## v5.2 音色仿写支持 (Current, started 2026-07-01)

**核心目标：** 在转写阶段自动提取原视频说话人音色，通过 SiliconFlow API 注册自定义音色并用于 TTS 合成，让中文配音保留原说话人的声音特征。

**关键架构决策：**
- Backend first, frontend last (strict dependency chain)
- 提取逻辑复用现有 `_extract_speech_sample`，不依赖 demucs（用 original_audio.wav）
- 音色 URI 持久化到 Video 模型，跨阶段共享
- 克隆失败回退到预设音色，不影响现有流程

**Granularity:** Standard (3 phases)
**Coverage:** 9/9 v5.2 requirements mapped

---

### Phases

- [x] **Phase 12: Voice Sample Extraction** — 转写阶段自动音色提取 + 持久化 (3/3 reqs)
- [x] **Phase 13: Voice Clone TTS Integration** — TTS 管线音色克隆集成 + 回退 (4/4 reqs)
- [x] **Phase 14: Voice Selection UI** — 前端音色模式选择 UI + 配置 (3/3 reqs)

---

### Phase Details

### Phase 12: Voice Sample Extraction

**Goal:** 转写阶段（TRANSCRIBE）自动从 original_audio.wav 提取高质量人声片段并持久化保存

**Depends on:** Nothing (first phase of v5.2)

**Requirements:** VOICE-01, VOICE-02, VOICE-03

**Success Criteria** (what must be TRUE):
1. `dubbing/voice_cloner.py` 的 `_extract_speech_sample` 支持以 `original_audio.wav` 为输入（不依赖 `vocals.wav`）
2. 转写阶段（`_handle_transcribe`, scheduler.py）完成后，自动调用提取逻辑
3. 提取的 `clone_sample.wav` 持久化保存到 `{work_dir}/`，不被删除
4. 提取的人声片段时长在 5-15s 范围内，Whisper 置信度 > 0.5
5. 现有测试全部通过

**Plans**: 2 plans

```
Plans:
- [ ] 12-01-PLAN.md — VoiceCloner refactor: fallback audio source + persistence + config seeder
- [ ] 12-02-PLAN.md — Transcribe integration: voice extraction during TRANSCRIBE + synthesize fallback
```

### Phase 13: Voice Clone TTS Integration ✅

**Goal:** 提取的参考音频上传到 SiliconFlow 注册音色，TTS 管线使用克隆音色合成中文配音

**Depends on:** Phase 12 (需要 clone_sample.wav 存在作为输入)

**Requirements:** CLONE-01, CLONE-02, CLONE-03, CLONE-04

**Status:** Complete (2026-07-01) — implemented as part of Phase 12. All 5 success criteria met.

**Success Criteria** (what must be TRUE):
1. `clone_sample.wav` 自动上传到 SiliconFlow `POST /uploads/audio/voice`，成功获取 URI ✅
2. URI 持久化写入 `Video.cloned_voice_uri` 字段（当前已有此字段） ✅
3. TTS 合成阶段 (`_handle_synthesize`) 检测到克隆 URI 时优先使用，传给 `SiliconFlowTTSProvider.synthesize(voice=URI)` ✅
4. 克隆失败（API 错误、URI 不存在等）时自动回退到预设音色（`tts_voice_simple`） ✅
5. `voice_clone_enabled` config 控制是否启用克隆流程 ✅

### Phase 14: Voice Selection UI ✅

**Goal:** 任务创建界面支持「预设音色/克隆原声」模式选择，配置流到后端

**Depends on:** Phase 13 (需要后端 TTS 克隆逻辑就绪)

**Requirements:** UI-01, UI-02, UI-03

**Status:** Complete (2026-07-01)

**Success Criteria** (what must be TRUE):
1. DubCreateDialog Step 2 增加一个「音色模式」el-radio-group：预设音色 / 克隆原声 ✅
2. 「预设音色」模式下保留现有音色下拉选择 ✅
3. 「克隆原声」模式下自动开启 `voice_clone_enabled`，任务表现克隆标识 ✅
4. 已有克隆音色的视频，后续任务自动默认使用克隆模式 ✅（logic in persistCfg + synthesize existing_uri check）
5. SettingsView 同步增加音色模式配置项，保持全局默认值一致 （deferred — 默认 preset 已足够）

---

### Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 12. Voice Sample Extraction | 2/2 | Complete | 2026-07-01 |
| 13. Voice Clone TTS Integration | 0/0 | Complete | 2026-07-01 |
| 14. Voice Selection UI | 1/1 | Complete | 2026-07-01 |

---

## 已归档里程碑

### v5.0 开源化深度改造 — Done (2026-06-29)

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

*Last updated: 2026-06-29 — Phase 10 Plan 03 completed (Phase 10: 3/3 plans, Complete). All 13 plans across v5.1 complete.*
