# You2Bili - 项目路线图

## v4.0 智能选题与内容追踪 (Current)

**核心目标：** 从"被动加工"升级为"主动发现"——自动挖掘 YouTube 上最适合翻译搬运、最能吸引中文观众的优质视频，支持自定义评分规则，让用户知道"搬什么"而不是"怎么搬"。

---

## v3.0 已归档 (2026-06-23) — UX 重设计

**核心目标：** 把"功能能用"升级为"新用户 5 分钟内完成首次配音发布"。Dashboard 中心化 + 3 项导航 + 向导式新建任务。

**2 个 Phase 完成：**
- Phase 11: 现状总结 + 设计方案 + 多角度 review → `.planning/DESIGN.md`
- Phase 12: 实现新设计 → 10 文件改动（Dashboard/Tasks/Settings/MainLayout/DubCreateDialog/SubtitleEditor + 新 PlatformLoginDrawer + theme.css）

归档至 `.planning/milestones/v3.0-*/`。

---

## v2.0 已归档 (2026-06-22)
端到端翻译配音管线 + 平台发布 + 完整文档，238 backend tests pass。

---

## v1.0 已完成 (Phase 1-3, 2026-06-15)
项目骨架（已被 v2.0 Phase 4 替换）。

---

## 已知技术债（carried forward）

- `test_phase10_docs_and_scripts_exist` 路径过时（v2.0 归档后未更新）
- `test_resolve_transcript_text_empty_segments` Phase 8 edge case bug
- 后端 `GET /api/tasks` 缺 `thumbnail_url` 字段（v3.0 DESIGN.md R8 待加）
- `GET /api/onboarding/status` endpoint 未实现
- Frontend bundle 1.19MB，未 code-split
