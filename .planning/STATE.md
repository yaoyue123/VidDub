---
gsd_state_version: 1.0
milestone: v5.1
milestone_name: Discover 页面重构与 Bug 修复
status: planning
last_updated: "2026-06-29T11:55:27.704Z"
last_activity: 2026-06-29
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Current Milestone: v5.0 开源化深度改造 ✅ COMPLETE (6/6)

Updated: 2026-06-29

---

## Project Reference

**Core Value:** 把"中文观众想看的优质 YouTube 内容"自动搬运到国内平台——下载、翻译、配音、字幕、发布全流程自动化。v5.0 把项目从"自用工具"升级为"开源项目"：清晰结构、明确接口、社区文档。

**Current Focus:** All 6 phases complete ✅. v5.0 开源化深度改造 — DONE. Ready for tag v5.0.0.

---

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-06-29 — Milestone v5.1 started

## v5.0 Roadmap Summary

| Phase | Goal | Reqs | Depends on |
|-------|------|------|------------|
| 1. Repo hygiene & directory structure | 干净的根目录与 backend/ | STRUCT-01..06, BUILD-03 | — |
| 2. Dead code & redundancy removal | 无死代码、无重复实现 | DEAD-01..05 | Phase 1 |
| 3. Configuration system unification | 单一配置源 | CONFIG-01..03 | Phase 2 |
| 4. Backend API normalization | 20 路由遵循同一规范 | API-01..05 | Phase 3 |
| 5. Frontend cleanup | 修 bug + 类型化 API + 死视图清理 | FE-01..03 | Phase 4 |
| 6. Documentation & build consolidation | 开源级文档 + 启动脚本整合 | DOC-01..06, BUILD-01,02 | Phases 1-5 |

**Coverage:** 31/31 v5.0 requirements mapped + SAFE-01/02/03 distributed as success criteria across all phases.

---

## Performance Metrics

- Phases completed: 0 / 6
- Plans completed: 0
- Tests passing baseline: pending (will be established in Phase 1)
- Open blockers: 0

---

## Accumulated Context

### Decisions (carried forward)

- D-01: API Key 直接放 .env（不加密）
- D-05: 放弃 BGM 保留，整轨替换中文配音
- D-09: atempo + pad/trim 时间对齐，0.7-1.5x
- D-13/D-14: 状态机去除 separating/mixed
- D-17: STT 改用本地 Whisper（SiliconFlow 无 segment 时间戳）
- v3.0 DESIGN.md §6 修订定稿：13 项采纳 + 4 项延后
- v3.0 主色 indigo-600 #4F46E5（避开 Element Plus 默认 blue generic 感）
- **v5.0-D1: `--reset-phase-numbers`** — 给开源改造一个干净的相位编号起点（从 1 起重新计数）
- **v5.0-D2: SAFE-* 不单独成 phase** — 每个 phase 必须包含"无回归"成功标准（测试通过、构建成功、端到端 smoke 通过）
- **v5.0-D3: 不增加新功能** — 仅做改造、清理、文档化

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260629-ln4 | Execute v5.0 Phase 1: repo hygiene & directory structure cleanup | 2026-06-29 | 35ab289 | [260629-ln4-execute-v5-0-phase-1-repo-hygiene-direct](./quick/260629-ln4-execute-v5-0-phase-1-repo-hygiene-direct/) |

### Active Todos

- [x] Phase 1: Repo hygiene & directory structure ✅ (4 commits, STRUCT-01..06 + BUILD-03 done)
- [ ] Phase 2: Dead code & redundancy removal (`/gsd-quick` or `/gsd-autonomous --from 2`)
- [ ] 预存 2 个 stale tests（`test_phase10_docs_and_scripts_exist`、`test_resolve_transcript_text_empty_segments`）在 Phase 4 或 Phase 6 修复或标记 xfail

### Blockers

无

---

## Known Issues (carried forward)

- `backend/backend/` 嵌套重复目录待清理 (Phase 1)
- 运行时产物入库：`venv/`、`dist/`、`*.log`、`bilibili_qr.png`、`downloads/` (Phase 1)
- 配置系统 4 套并存 (Phase 3)
- 旧版 API 与新版 API 并存：`dubbing.py`↔`dub.py`、`upload.py`↔`publish.py` (Phase 2/4)
- 死代码：`_archived/`、`tts_service.py`、`translation_service.py`、重复 TTS 实现 (Phase 2)
- `social-auto-upload/` 中重复小红书上传器 + `conf.py` 敏感文件入库 (Phase 2)
- 前端活跃 bug：`taskStore.ts` 与 `constants.ts` 常量重复定义 (Phase 5)
- 5 个启动脚本散乱 (Phase 6)
- Frontend bundle 1.19MB — code-split deferred (v6+)

---

## Session Continuity

**Last activity:** 2026-06-29 — Phase 1 complete ✅ (4 commits, 275 tests pass, npm build OK)

**Next steps:**

1. Phase 2: Dead code & redundancy removal (`/gsd-quick "Phase 2: dead code removal"` or resume via `/gsd-autonomous --from 2`)
2. Continue through Phases 3-6 in dependency order

**Phase 1 deliverables:**

- Deleted: `_check_db.py`, `backend/backend/` (stale credentials removed), `backend/bilibili_qr.png`
- Moved: `biliup_login.py` → `scripts/`, `test_douyin_publish.py` → `backend/tests/`
- Created: `docs/SOCIAL_AUTO_UPLOAD.md`, `docs/DESIGN.md`, `docs/REFACTOR_PLAN.md`
- Updated: `.gitignore` (+ `.pytest_cache/`, `htmlcov/`, `backend/*.png`)
- No regression: 275 tests passed (unchanged from baseline), `npm run build` succeeds
