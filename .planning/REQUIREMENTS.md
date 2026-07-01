# Requirements: You2Bili

**Core Value:** 把"中文观众想看的优质 YouTube 内容"自动搬运到国内平台——下载、翻译、配音、字幕、发布全流程自动化。

---

## v5.1 Discover 页面重构与 Bug 修复

**Defined:** 2026-06-29
**Goal:** 将 discover 页面从旧推荐系统重构为多维度内容跟踪系统，支持关键词/频道跟踪与筛选，修复封面和下载目录问题。

### TRACK — 内容跟踪

- [x] **TRACK-01**: 用户可以通过关键词搜索 YouTube 视频并查看即时结果
- [x] **TRACK-02**: 用户可以跟踪 YouTube 博主/频道，查看其最新视频列表
- [x] **TRACK-03**: 用户可以为每个跟踪源设置筛选条件（最低/最高播放量、时长范围、发布时间窗口）
- [x] **TRACK-04**: 用户可以将搜索结果保存为跟踪源，支持后续自动扫描
- [x] **TRACK-05**: 系统自动去重——已下载和已发现的视频不会重复出现

### SCAN — 自动扫描与调度

- [x] **SCAN-01**: 系统通过统一协调器自动扫描所有已保存的跟踪源，按配置的时间间隔执行
- [x] **SCAN-02**: 每个跟踪源记录扫描历史（上次扫描时间、发现数量、状态），用户可查看
- [x] **SCAN-03**: 用户可手动触发即时搜索/扫描，无需等待定时任务

### UI — Discover 页面重构

- [x] **UI-01**: Discover 页面重写为多标签页界面（搜索 / 关键词跟踪 / 频道跟踪）
- [x] **UI-02**: 搜索结果以视频卡片网格展示，包含缩略图、标题、播放量、时长、发布时间
- [x] **UI-03**: 视频卡片支持一键"加入搬运管线"操作（跳转到创建任务页面并预填视频信息）
- [x] **UI-04**: 支持跟踪源的增删改查管理（添加、编辑、删除、启用/禁用）

### CLEANUP — 旧代码清理

- [x] **CLEANUP-01**: 移除 v4.0 评分引擎后端代码（scoring/ 目录、scoringApi、rulesApi、VideoScore 模型、ContentRule 模型、/api/scoring/ 路由、/api/rules/ 路由）
- [x] **CLEANUP-02**: 移除前端旧推荐系统引用（scoringApi 调用、rulesApi 调用、旧 DiscoverView 内联 API 逻辑）

### BUG — Bug 修复

- [x] **BUG-01**: YouTube 视频封面正常显示——后端缩略图代理（i.ytimg.com 通过 FastAPI 流式转发 + CORS 头）
- [x] **BUG-02**: 下载目录去重——消除重复的 downloads 目录，统一为单一下载路径源

### INFRA — 基础设施

- [x] **INFRA-01**: 创建统一的 yt-dlp 封装层（YtDlpWrapper），带全局限速器防止 YouTube 429/403 限流，集中管理 cookie 和 extractor-args
- [ ] **INFRA-02**: SQLite 数据库优化——启用 WAL 模式、设置 busy_timeout、添加跟踪查询所需的索引

---

## v5.2 音色仿写支持

**Defined:** 2026-07-01
**Goal:** 在转写阶段自动提取原视频说话人音色，通过 SiliconFlow API 实现 TTS 音色克隆，让配音保留原说话人声音特征。

### VOICE — 自动音色提取

- [ ] **VOICE-01**: 转写（TRANSCRIBE）阶段从 `original_audio.wav` 自动提取高质量人声片段（5-15s）作为音色参考样本
- [ ] **VOICE-02**: 参考音频持久化保存到 `{work_dir}/clone_sample.wav`（不再用完即删）
- [ ] **VOICE-03**: 提取算法复用 `_extract_speech_sample` 逻辑，按 Whisper 置信度评分选择最佳片段

### CLONE — 音色克隆与 TTS

- [ ] **CLONE-01**: 提取的参考音频自动上传到 SiliconFlow（`POST /v1/uploads/audio/voice`）注册自定义音色
- [ ] **CLONE-02**: 注册成功后获取 URI 存储在 `Video.cloned_voice_uri` 字段，持久化跨阶段使用
- [ ] **CLONE-03**: TTS 管线（`SiliconFlowTTSProvider`）支持使用克隆音色 URI 作为 `voice` 参数
- [ ] **CLONE-04**: `voice_clone_enabled` 开启时，合成阶段优先使用克隆音色；克隆失败则回退到预设音色

### UI — 音色选择与配置

- [ ] **UI-01**: 任务创建对话框（DubCreateDialog）Step 2 增加「音色模式」选项：预设音色 / 克隆原声
- [ ] **UI-02**: 「克隆原声」模式下自动提取并注册原视频说话人音色，合成时使用克隆音色
- [ ] **UI-03**: 克隆成功后该视频的后续任务默认使用已注册的克隆音色

---

## Deferred (post-v5.2)

- Playlist 跟踪（yt-dlp playlist 提取 + 顺序保持）
- Trending 热点跟踪（yt-dlp explore 页面 + 定期快照）
- Topic 主题跟踪（标签 + 多关键词聚合）
- 批量关键词导入（textarea 逐行解析）
- 跨维度去重 badge（同一视频通过多个来源发现）
- 自动禁用反复出错的跟踪源

## Out of Scope

| Feature | Reason |
|---------|--------|
| v4.0 五维评分引擎 | v5.1 用简单筛选替代，不做智能评分 |
| v4.0 自定义规则引擎 | 不在本 milestone 范围 |
| Playlist / Trending / Topic 跟踪 | 推迟到 post-v5.2，先聚焦音色仿写 |
| YouTube Data API v3 集成 | yt-dlp 爬取已足够；API key 管理 + 配额限制对个人工具不划算 |
| 本地模型（Ollama/LM Studio） | 全部使用硅基流动云端 API |
| 多用户系统 | 个人自用工具 |
| 移动端 App | 仅 Web 界面 |
| MOSS-TTSD 双说话人对话 | 本 milestone 聚焦单说话人克隆，对话模式推迟 |
| Speaker diarization（多说话人分离） | 本 milestone 无需区分说话人 |
| 手动上传参考音频克隆 | 自动提取即可，不增加手动上传复杂度 |
| 音色管理页面（增删改查） | 简化 UI，统一放在配置下拉框中 |

---

## v5.0 开源化深度改造 (COMPLETED ✅)

> v5.0 requirements are all validated. Kept for historical traceability.

### STRUCT — 目录结构清理
- [x] **STRUCT-01~06**: 仓库结构清理 ✅
### DEAD — 死代码删除
- [x] **DEAD-01~05**: 死代码清除 ✅
### CONFIG — 配置统一
- [x] **CONFIG-01~03**: 配置系统统一 ✅
### API — 后端 API 规范化
- [x] **API-01~05**: API 规范化 ✅
### FE — 前端清理
- [x] **FE-01~03**: 前端清理 ✅
### DOC — 文档重写
- [x] **DOC-01~06**: 开源文档 ✅
### BUILD — 构建整合
- [x] **BUILD-01~03**: 构建脚本整合 ✅

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 7 | Done |
| INFRA-02 | Phase 7 | Complete | 07-01-PLAN.md |
| CLEANUP-01 | Phase 7 | Pending |
| CLEANUP-02 | Phase 7 | Complete | 07-04-PLAN.md |
| TRACK-01 | Phase 8 | Done | 08-01-PLAN.md |
| TRACK-02 | Phase 8 | Done | 08-01-PLAN.md |
| TRACK-05 | Phase 8 | Done | 08-02-PLAN.md |
| SCAN-01 | Phase 8 | Done | 08-02-PLAN.md |
| SCAN-02 | Phase 8 | Done | 08-01-PLAN.md, 08-02-PLAN.md |
| TRACK-03 | Phase 9 | Done | 09-01-PLAN.md |
| TRACK-04 | Phase 9 | Done | 09-01-PLAN.md |
| SCAN-03 | Phase 9 | Done | 09-02-PLAN.md |
| BUG-01 | Phase 9 | Done | 09-02-PLAN.md |
| UI-01 | Phase 10 | Complete | 10-03-PLAN.md (DiscoverView multi-tab rewrite) |
| UI-02 | Phase 10 | Complete | 10-02-PLAN.md, 10-03-PLAN.md |
| UI-03 | Phase 10 | Complete | 10-02-PLAN.md, 10-03-PLAN.md |
| UI-04 | Phase 10 | Complete | 10-03-PLAN.md (DiscoverView multi-tab rewrite) |
| BUG-02 | Phase 11 | Complete | 11-01-PLAN.md |

**Coverage:**
- v5.1 requirements: 18 total — all Complete ✅
- v5.2 requirements: 9 total — defining...
- Mapped: 0 (pending roadmap creation)
- Unmapped: 9

---
*Requirements defined: 2026-06-29*
*Last updated: 2026-07-01 — Added v5.2 音色仿写 support requirements (9 requirements in VOICE/CLONE/UI categories)*
