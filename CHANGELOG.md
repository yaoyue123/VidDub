# Changelog

记录每个 Phase（里程碑）的交付物。详细技术细节请参见 `.planning/phases/{phase}/0*-SUMMARY.md`。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/)。版本号遵循 v2.0.x（每个 Phase 一个子版本）。

---

## [v2.0.10] — 2026-06-22 — Phase 10: 部署脚本 + 完整文档

- 新增 `setup.ps1` / `setup.sh` 一键环境初始化脚本（检查 Python/Node/ffmpeg/yt-dlp、创建 venv、装后端依赖、装 Playwright Chromium、装前端依赖、预下载 Whisper 模型、跑 Alembic 迁移、生成 `.env`）
- 新增 `start.ps1` / `start.sh` 一键启动脚本（uvicorn + vite dev）
- 新增 `README.md`（中文项目总览 + 3 步快速开始 + 目录结构 + 技术栈表 + 开发者文档链接）
- 新增 `CHANGELOG.md`（按 Phase 列交付物）
- 新增 `docs/ARCHITECTURE.md`（Mermaid 架构图 + 数据流 + 模块依赖 + Video.status 状态机）
- 新增 `docs/API.md`（REST 端点分组 + WebSocket 事件清单）
- 新增 `docs/CONFIGURATION.md`（`.env` 变量 + 全部 `app_config` 配置项分组说明）
- 新增 `docs/TROUBLESHOOTING.md`（API Key、限流、Whisper 下载、ffmpeg、Playwright、Windows 路径、SQLite 锁等常见问题）
- 新增 `docs/DEPLOYMENT.md`（Linux systemd / Windows Service / nginx 反代 + 备份策略）
- 新增 `backend/tests/integration/test_phase10_e2e.py` 端到端 smoke test（mock 全链路：API POST /api/dub → poll status → assert reaches `composed`）
- 全部 222 个旧测试 + 1 skipped + 1 个新 Phase 10 测试通过；前端 `npm run build` 通过

## [v2.0.9] — 2026-06-22 — Phase 9: 定时任务 + 批量管理

- 引入 APScheduler 3.10，`ChannelScanner` 在 FastAPI lifespan 内启停
- 新增 `channels` / `scan_logs` 表，`videos` 加 `deleted_at` / `channel_id` / `source` 列（迁移 `c9d0e1f2a3b4`）
- `services/channel_scanner.py` — 按频道间隔扫描 → 应用过滤（min_views / duration）→ 去重 → 自动建 Video + download Task
- 新增 7 个 channel API 端点 + `POST /api/tasks/batch`（pause/resume/retry/delete）+ `GET /api/export/tasks?format=csv|json` 流式导出
- 前端新增 `/channels` 频道管理页（增/删/改 + 扫描日志抽屉）+ TasksView 多选批量工具栏 + 多维筛选
- 软删除：默认隐藏 `deleted_at IS NOT NULL` 的视频
- 222 个 backend 测试通过（Phase 9 新增 18 个）+ 1 个 `requires_network` 跳过

## [v2.0.8] — 2026-06-22 — Phase 8: AI 智能标题与标签

- 使用 SiliconFlow Chat **JSON mode** 一次返回 `{titles:[5], tags:[8], summary_zh}`
- JSON mode 失败时自动回退到 `[TITLES]...[/TITLES]` 文本格式
- 新增 4 列：`ai_title_candidates` / `ai_tags_candidates` / `title_chosen` / `tags_chosen`（迁移 `b8c9d0e1f2a3`）
- 新增 3 个 API：`POST /api/title/{id}/generate`、`GET /api/title/{id}`、`PUT /api/title/{id}`
- scheduler 在 compose 完成后同步触发 `_handle_generate_title`，发布时 `prepare_publish_fields` 优先用用户选定值
- 前端新增 `AiTitleSelector.vue` 弹窗（radio 单选标题 + chip 多选标签 + 自定义输入 + 重新生成）+ Settings 新 AI 标题 tab
- 容错全面：缺字段 / 类型错 / CSV 字符串标签自动修正
- 213 个测试通过（Phase 8 新增 34 个）

## [v2.0.7] — 2026-06-22 — Phase 7: 平台自动发布

- 新增 `publish_records` 表 + 迁移 `a1b2c3d4e5f6`（幂等 CREATE TABLE IF NOT EXISTS）
- `services/publish/{base,bilibili,ixigua,manager,title_translate}.py` — 抽象基类 + 两个平台 publisher + SiliconFlow Chat 标题翻译
- 6 个 REST 端点：trigger / auto / list / detail / retry
- scheduler chain 新增 `_handle_publish`，在 `auto_publish_enabled=true` 时自动跑（依赖 Phase 6 storage_state）
- 4 个 WebSocket 事件：`publish_start` / `publish_progress` / `publish_complete` / `publish_error`（含 `needs_relogin`）
- 前端新增 `PublishHistoryView.vue`、TasksView 发布列、SettingsView 发布配置区
- Playwright headed 模式（无图形界面环境会失败 — 见 DEPLOYMENT.md）
- 179 个测试通过（Phase 7 新增 27 个）

## [v2.0.6] — 2026-06-22 — Phase 6: 平台自动登录

- 新增 `services/platform/{base,manager,bilibili,ixigua}.py` — 平台登录抽象 + 两平台实现
- 哔哩哔哩走官方 HTTP QR API（`/x/passport-login/web/qrcode/generate` + `/poll`），无需 Playwright；本地用 `qrcode` 包把 URL 编码成 PNG
- 西瓜视频使用 Playwright headed Chromium（无官方 QR HTTP API）+ DOM 启发式检测登录态
- 6 个 REST 端点 + 3 个 WebSocket 事件（`platform_qr_update` / `platform_login_status` / `platform_login_expired`）
- 后台 `_login_poll_loop`（2s 检测 + 30s 刷新 QR）+ 定时 `_platform_check_loop`（每 30 分钟检测过期）
- `storage_state.json` 持久化 cookies，重启不丢失；多账号命名 `{platform}_{account_id}_storage_state.json` 已预留
- 前端 `PlatformLoginView.vue` 二维码扫码页 + Dashboard 平台卡片 + Settings 平台管理 tab
- 152 个测试通过（Phase 6 新增 28 个）

## [v2.0.5] — 2026-06-22 — Phase 5: Web UI 改造与配音可视化

- `TasksView.vue` 全重写：每步状态徽章 + 进度条 + 试听 popover + 重新执行/恢复按钮
- `SettingsView.vue` 全重写：5 个 tab（SiliconFlow / STT / TTS / Translate / Advanced）+ 密码 mask + 连通性测试
- `SubtitleEditorView.vue` 全重写：双语两列对照 + 行内编辑自动保存 + 单行重新翻译 + SRT/双语 SRT 导出
- `DashboardView.vue` 全重写：4 个统计卡片 + 最近 5 任务 + 失败重试 + 新建配音对话框
- 新增组件：`DubCreateDialog.vue`、`AudioPreview.vue`
- 新增后端端点：`POST /api/config/test-siliconflow`、`POST /api/subtitles/{id}/retranslate`、`GET /api/stats/dashboard`、`GET /api/dub/{id}/preview/{kind}`、静态文件挂载 `/static/downloads`
- 124 个测试通过（Phase 5 新增 11 个）

## [v2.0.4] — 2026-06-17 — Phase 4: 核心翻译配音管线 (MVP)

- **端到端跑通**：YouTube URL → 中文配音 mp4（6 步管线：Download → Extract audio → Whisper STT → Translate → TTS per segment + atempo 对齐 → Stitch + Compose）
- CLI：`python -m app.cli dub <youtube_url>`、`status`、`resume`
- REST API：`POST /api/dub`、`GET /api/dub/{id}`、`/download`、`/subtitle`、`/resume`
- 新增 `services/siliconflow/{client,translate,tts}.py`（httpx + tenacity 重试）
- 新增 `services/dubbing/{pipeline,ffmpeg,alignment,stitcher,composer,paths}.py`（ffmpeg 编排层）
- Alembic 迁移 `f8a9b0c3d1e2`（非破坏性、幂等）
- 翻译批量请求失败时自动回退到逐段单独请求（Rule 1 bug 修复）
- STT 改用本地 Whisper（D-17 pivot）；BGM 保留弃用（D-05 pivot）
- 60 个新测试 + 51 个旧测试全部通过；真 E2E（SiliconFlow live TTS + Translate）验证通过；final.mp4 duration 误差 <100ms

## [v1.0.3] — 2026-06-15 — Phase 3: Whisper 转写与字幕（旧管线，v2.0 已重构）

- `WhisperService` 本地 Whisper 集成（Phase 4 复用）
- `Subtitle` 模型 + Alembic 迁移 + Subtitle API
- scheduler `_handle_transcribe` handler
- 前端 `SubtitleEditorView`（Phase 5 全重写）

## [v1.0.2] — 2026-06-15 — Phase 2: 视频发现与下载

- `YoutubeService`（搜索 + 频道扫描 + yt-dlp 下载）
- `TaskScheduler` 任务调度器（Phase 4 重构）
- `ConfigSeeder` 配置 seed 机制
- Discovery API + `POST /api/videos`

## [v1.0.1] — 2026-06-15 — Phase 1: 项目骨架 + Web UI 基础

- FastAPI + SQLAlchemy async + Alembic + Pydantic Settings 后端
- Vue 3 + Vite + TypeScript + Element Plus + Pinia 前端
- 4 个基础视图（Dashboard / Tasks / Settings / Subtitle Editor）
- WebSocket 实时进度推送
- 18 个 REST 端点 + 数据库模型（Video / Task / Config / Subtitle）

---

## v2.0 Milestone — 完成清单 (2026-06-22)

- [x] Phase 4 核心翻译配音管线（端到端 mp4 输出）
- [x] Phase 5 Web UI 改造（无 CLI 操作）
- [x] Phase 6 平台自动登录（西瓜 + 哔哩哔哩扫码）
- [x] Phase 7 平台自动发布（Playwright headed）
- [x] Phase 8 AI 智能标题与标签（JSON mode）
- [x] Phase 9 定时任务 + 批量管理（APScheduler）
- [x] Phase 10 部署脚本 + 完整文档（本文件）

**当前状态：v2.0 milestone 已完成 — READY FOR AUDIT。**

---

*所有日期基于本地时间 (UTC+8)。每个 Phase 的技术细节、决策、偏差、gotcha 见对应 `.planning/phases/NN-xxx/NN-01-SUMMARY.md`。*
