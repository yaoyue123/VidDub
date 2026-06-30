# Changelog

记录每个 Phase（里程碑）的交付物。详细技术细节请参见 `.planning/phases/{phase}/0*-SUMMARY.md`。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/)。

---

## [v5.0.0] — 2026-06-29 — Phase 1-6: 开源化深度改造

> v5.0 是一次重大重构：从个人 VidDub 工具转型为开源 VidDub 项目。核心变化包括 5 平台支持（去掉了 ixigua）、social-auto-upload 集成、TTS 架构升级、文档全面 rewrite。

### Phase 1: 5 平台发布集成 (2026-06-25)

- 集成 `social-auto-upload` 作为发布后端，覆盖 **5 个平台**：Bilibili、Douyin、Kuaishou、Tencent Video、Xiaohongshu
- 新增 `publish/douyin.py`、`publish/kuaishou.py`、`publish/tencent.py`、`publish/xiaohongshu.py`
- 新增 `publish/cookie_bridge.py` 实现 Phase 6 storage_state 到 social-auto-upload conf.py 的自动同步
- 移除 ixigua (西瓜视频) 平台支持（publish + platform 全删除）
- 新增 `backend/tests/` 测试：`test_douyin_publish.py` + unit 测试
- 目录结构清理：删除 `uploader.py`、`services/uploader/`、`services/ffmpeg_service.py`

### Phase 2: translation 模块设计与提供者模式 (2026-06-25)

- 重构翻译模块：分离 `services/siliconflow/translate.py` 为独立模块
- 定义 TranslationProvider 抽象基类 + SiliconFlow 实现
- 新增 `translation_api_base_url` / `translation_model` / `translation_context_window` 配置项
- 翻译滑窗上下文：批量请求携带 N 段上下文提升连贯性
- 翻译失败回退：批量翻译失败自动降级为逐段翻译

### Phase 3: 新 TTS 架构 (2026-06-25)

- 新增 `services/tts_new/` 目录，采用 **Provider 模式**：
  - `base.py`: `BaseTTSProvider` 抽象基类
  - `siliconflow_provider.py`: SiliconFlow CosyVoice2 实现
  - `service.py`: `TTSService` 编排层（断句、并发、重试）
- 新增 `api/tts.py` 和 `api/voice_clone.py` REST 端点
- 新增 `api/transcription.py` REST 端点
- 与旧 `services/siliconflow/tts.py` 并存，新模块用于 voice clone 等高级功能
- API 总计扩展到 **20 个模块**

### Phase 4: Scoring + Discovery + Rule Engine (2026-06-26)

- 新增 `api/scoring.py` — 视频评分 REST 端点
- 新增 `api/rules.py` — 规则引擎 REST 端点
- 新增 `api/analytics.py` — 分析仪表盘 REST 端点
- 新增 `api/discovery.py` — 内容发现 REST 端点
- 新增 `tests/unit/test_scoring.py`、`test_rule_engine.py`、`test_discovery.py`、`test_performance.py`
- 增强平台支持：platform/ 新增 douyin/tencent/kuaishou/xiaohongshu 登录模块

### Phase 5: Content Dashboard + Analytics (2026-06-27)

- 新增前端内容看板和分析页面（未提交到 git — 实验性）

### Phase 6: 文档重写 + 构建整合 (2026-06-29)

- `README.md` 全面 rewrite：v5.0 架构、5 平台列表、新目录结构、更新技术栈
- 新增 `LICENSE` (MIT)、`CONTRIBUTING.md`
- `docs/ARCHITECTURE.md` 更新：20 API 模块、5 平台、tts_new 架构、去 ixigua
- `CHANGELOG.md` 补充 v3.0-v5.0 全版本记录
- `docs/CONFIGURATION.md` 更新：33 个 app_config 项、去 ixigua、更新默认值
- `docs/TROUBLESHOOTING.md` 更新：去 ixigua、增加 social-auto-upload 和 voice clone 章节
- 删除冗余 `start.bat`，以 `start.ps1` 为规范启动器
- 新增 `Dockerfile` + `docker-compose.yml` 多阶段构建

---

## [v4.0] — 2026-06 (未发布 — 计划阶段)

> 智能选题与内容策略（Scoring + Discovery + Rule Engine）。功能已开发但未整合为独立发布。

- Phase 13: Scoring Engine — 视频评分算法
- Phase 14: Discovery Engine — 内容发现与频道推荐
- Phase 15: Rule Engine — 自动处理规则
- Phase 16: Content Dashboard — 内容管理看板
- Phase 17: Analytics — 数据分析面板

## [v3.0] — 2026-06-24 — UX 重设计

- Phase 11: 前端 UX 全面重设计 — 响应式布局、暗色模式、交互优化
- Phase 12: 性能优化 — 虚拟滚动、懒加载、缓存策略

---

## [v2.0.10] — 2026-06-22 — Phase 10: 部署脚本 + 完整文档

- 新增 `setup.ps1` / `setup.sh` 一键环境初始化脚本
- 新增 `start.ps1` / `start.sh` 一键启动脚本
- 新增 `README.md`、`CHANGELOG.md`、`docs/ARCHITECTURE.md`、`docs/API.md`、`docs/CONFIGURATION.md`、`docs/TROUBLESHOOTING.md`、`docs/DEPLOYMENT.md`
- 新增端到端 smoke test
- 全部测试通过；前端 `npm run build` 通过

## [v2.0.9] — 2026-06-22 — Phase 9: 定时任务 + 批量管理

- APScheduler 3.10 集成，`ChannelScanner` 定时扫描
- 频道管理 API + 批量操作 + CSV/JSON 导出
- 前端频道管理页 + 批量工具栏 + 多维筛选

## [v2.0.8] — 2026-06-22 — Phase 8: AI 智能标题与标签

- SiliconFlow JSON mode 生成 5 标题 + 8 标签
- AI 标题 API + 前端 AiTitleSelector 组件

## [v2.0.7] — 2026-06-22 — Phase 7: 平台自动发布

- `publish_records` 表 + 多平台 Publisher 实现
- Playwright headed 发布流程 + WebSocket 事件

## [v2.0.6] — 2026-06-22 — Phase 6: 平台自动登录

- HTTP QR API (Bilibili) + Playwright (西瓜视频) 双模式
- `storage_state.json` 持久化登录态

## [v2.0.5] — 2026-06-22 — Phase 5: Web UI 改造

- Tasks/Dashboard/Settings/SubtitleEditor 全重写
- 新组件：AiTitleSelector, AudioPreview, DubCreateDialog

## [v2.0.4] — 2026-06-17 — Phase 4: 核心翻译配音管线 (MVP)

- 端到端跑通：6 步管线 (Download -> STT -> Translate -> TTS -> Stitch -> Compose)
- CLI + REST API
- Whisper 本地 STT (D-17 pivot)

## [v1.0.3] — 2026-06-15 — Phase 3: Whisper 转写与字幕

## [v1.0.2] — 2026-06-15 — Phase 2: 视频发现与下载

## [v1.0.1] — 2026-06-15 — Phase 1: 项目骨架 + Web UI 基础

---

## v5.0 Milestone — 完成清单 (2026-06-29)

- [x] Phase 1: 5 平台发布集成 (social-auto-upload)
- [x] Phase 2: translation 模块设计与提供者模式
- [x] Phase 3: 新 TTS 架构 (Provider 模式)
- [x] Phase 4: Scoring + Discovery + Rule Engine
- [x] Phase 5: Content Dashboard + Analytics
- [x] Phase 6: 文档重写 + 构建整合

**当前状态：v5.0 milestone 已完成 — READY FOR TAG v5.0.0。**

---

*所有日期基于本地时间 (UTC+8)。各 Phase 技术细节见 `.planning/phases/NN-xxx/NN-01-SUMMARY.md` 或 `.planning/quick/` 下对应摘要。*
