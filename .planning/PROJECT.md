# You2Bili - YouTube 视频搬运工具

## What This Is

You2Bili 是一款开源工具，自动从 YouTube 发现、下载、翻译、配音并发布优质视频到国内平台（哔哩哔哩、西瓜视频）。完整的端到端管线：YouTube 下载 → 人声分离 → 转写 → 翻译 → 中文配音 → 字幕合成 → 多平台自动发布，配合 Web 管理界面可视化操作。面向中文观众的内容搬运场景，本地部署、社区共建。

## Core Value

把"中文观众想看的优质 YouTube 内容"自动搬运到国内平台——下载、翻译、配音、字幕、发布全流程自动化，让任何人都能轻松把英文/外语视频转化为中文内容。

## 目标用户

- **主要：** 个人创作者 / 内容搬运者（自用，本地部署）
- **v5.0 起：** 开源社区贡献者（可读、可改、可扩展）

## 开源定位 (v5.0)

v5.0 把项目从"自用工具"升级为"开源项目"：清晰的目录结构、明确的接口边界、社区友好的文档、合理的贡献流程。功能不变，但可读性和可维护性大幅提升。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Python FastAPI |
| 前端框架 | Vue 3 + Vite |
| UI 库 | Element Plus |
| 数据库 | SQLite (SQLAlchemy) |
| 视频下载 | yt-dlp |
| 语音识别 (STT) | 硅基流动 API (Audio Transcription) |
| 语音合成 (TTS) | 硅基流动 API (CosyVoice2-0.5B / MOSS-TTSD) |
| 翻译引擎 | 硅基流动 API (Chat Completions) |
| 语音克隆 | 硅基流动 API (Upload Voice) |
| 人声分离 | Demucs (htdemucs) |
| 音频/视频处理 | ffmpeg |
| 浏览器自动化 | Playwright / Selenium |
| 任务调度 | APScheduler |
| 部署方式 | Docker / 直接运行 |

## 核心功能

1. **视频发现与筛选** - 扫描频道/搜索，按播放量、时长、发布时间、点赞数等过滤
2. **视频下载** - 自动下载视频 + 原始字幕（如有）
3. **语音转写** - 硅基流动 API 转写为中文/双语字幕
4. **翻译** - 硅基流动 API 翻译字幕/标题/描述
5. **语音合成** - 硅基流动 API 生成中文配音（支持语音克隆）
6. **AI 标题生成** - 分析视频内容，自动生成爆款标题和标签
7. **平台自动登录** - 模拟浏览器登录西瓜视频/哔哩哔哩，无需人工输入 cookie
8. **平台自动发布** - 自动填写信息并发布视频
9. **定时任务** - 定时扫描频道、自动下载新视频
10. **批量任务管理** - 批量添加、暂停、重试任务
11. **Web 管理界面** - 任务管理、进度监控、配置管理

## Current Milestone: v5.0 开源化深度改造 (2026-06-29)

**Goal:** 把项目从"能跑但混乱的内部工具"改造为"结构清晰、文档完善、便于社区使用和贡献的开源项目"。功能不变，但代码质量、可读性、文档完整度大幅提升，达到可开源标准。

**改造范围：**
- **目录结构清理** — 移除嵌套重复 (`backend/backend/`)、运行时产物入库 (`venv/`, `dist/`, `*.log`, `bilibili_qr.png`)、vendored 与项目代码混杂
- **接口边界明确** — 统一后端 API 响应格式与错误处理，删除重复/旧版 API (`dubbing.py` vs `dub.py`、`upload.py` vs `publish.py`)，Pydantic response_model 规范化
- **死代码与冗余代码删除** — `_archived/`、`tts_service.py`、`translation_service.py`、重复 TTS 实现、重复小红书上传器等（详见 `REFACTOR_PLAN.md`）
- **配置系统统一** — 单一配置源（`.env` → `Settings` 类 → service），消除 4 套并存配置；前端 API base URL 可配置化
- **文档重写** — 面向开源用户的 README / ARCHITECTURE / CONTRIBUTING / LICENSE；删除过时/无效文档
- **构建与启动整合** — `.gitignore` 完善、5 个启动脚本整合、Docker 部署更新

**Pivot 背景:**
v2.0-v3.0 完成了功能（管线 + 平台发布 + UX），v4.0 智能选题规划后推迟。当前最大债务是**项目结构混乱、接口不清晰、死代码堆积**——这阻碍了开源。v5.0 优先解决可读性和可维护性，再谈新功能。

**Pre-existing analysis:** `.planning/REFACTOR_PLAN.md` 已在 2026-06-24 完成详细的代码扫描，列出了具体的死代码、冗余实现、接口问题——v5.0 直接基于该计划落地。

---

## Deferred Milestone: v4.0 智能选题与内容追踪

**Status:** Deferred (2026-06-29). Phase PLANs 已起草但未注册到 ROADMAP，从未执行。
**归档位置:** `.planning/milestones/v4.0-deferred/`

**v4.0 原目标:** 从"被动加工"升级为"主动发现"——五维评分 + 智能发现 + 规则引擎 + 内容追踪仪表盘。

**推迟原因:** 优先解决项目结构和代码质量（v5.0），让项目达到开源标准，再叠加新功能。

## 项目目录结构

```
you2bili/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI 路由
│   │   ├── core/         # 配置、数据库
│   │   ├── models/       # SQLAlchemy 模型
│   │   ├── services/     # 业务逻辑
│   │   │   ├── fetcher/      # 视频发现
│   │   │   ├── downloader/   # 视频下载
│   │   │   ├── transcriber/  # 硅基流动语音转写
│   │   │   ├── translator/   # 硅基流动翻译
│   │   │   ├── tts/          # 硅基流动语音合成
│   │   │   ├── ai_title/     # AI 标题生成
│   │   │   ├── browser/      # 浏览器自动化
│   │   │   └── uploader/     # 平台上传
│   │   └── tasks/        # 任务调度
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── views/        # 页面组件
│   │   ├── components/   # 通用组件
│   │   ├── stores/       # Pinia 状态
│   │   └── api/          # API 调用
│   └── package.json
├── docker-compose.yml
└── README.md
```

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ Phase 1: 项目骨架 + Web UI 基础
- ✓ Phase 2: 视频发现与下载
- ✓ Phase 3: Whisper 转写与字幕
- ✓ Phase 4-10: 端到端翻译配音管线 + 平台发布 + Docker
- ✓ Phase 11-12: UX 重设计

### Active (v5.0 开源化深度改造)

<!-- Current scope. Building toward these. -->

- [ ] 清晰的目录结构（无嵌套重复、运行时产物不入库、vendored 隔离）
- [ ] 统一的后端 API 接口（单一响应格式、单一错误处理、无重复/旧版端点）
- [ ] 配置系统单一真相源（.env → Settings → service，无 os.getenv 散落、无 DB 密钥冗余）
- [ ] 死代码/冗余代码清除（_archived、tts_service、translation_service、重复 TTS/上传器等）
- [ ] 开源级文档（README / ARCHITECTURE / CONTRIBUTING / LICENSE，删除过时文档）
- [ ] 完善的 .gitignore 与启动脚本（5 脚本整合、构建产物排除、Docker 更新）
- [ ] 现有功能无回归（端到端管线 / 平台发布 / Web UI 仍正常工作）

### Deferred (v4.0 — 恢复时再激活)

- 五维内容评分引擎（传播潜力/翻译适配/内容质量/市场潜力/制作成本）
- 智能发现引擎（频道推荐/趋势抓取/关键词挖掘/去重）
- 自定义规则引擎（可视化条件组合/权重调整/预设模板）
- 内容追踪仪表盘（推荐列表/频道面板/一键搬运）
- 搬运效果数据分析与评分反馈优化

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- 本地模型（Ollama/LM Studio）— 全部使用硅基流动云端 API
- 多用户系统 — 个人自用工具
- 移动端 App — 仅 Web 界面
- v5.0 内不做新功能开发 — 仅做改造、清理、文档

## Context

### 已完成功能 (Phase 1-12)
- 完整翻译配音管线：下载 → 人声分离(demucs) → Whisper 转写 → 硅基流动翻译 → CosyVoice2 TTS → 混音 → ffmpeg 合成
- 背景音分离 + 自动音色克隆 + 音色自动选择
- 双语字幕烧录版视频输出
- AI 智能标题与标签生成，多语言元数据管理
- 平台自动登录（西瓜/哔哩哔哩）+ 自动发布
- 定时频道扫描 + 批量任务管理
- Vue 3 管理界面（Dashboard 中心化 + 3 导航 + 向导式建任务）
- WebSocket 实时进度 + 字幕编辑器 + 发布历史
- Docker 部署 + 完整文档

### 技术决策
- 使用硅基流动 API 替代本地模型，降低部署复杂度
- 使用 Playwright 进行浏览器自动化，支持平台登录
- 使用 APScheduler 进行定时任务调度
- 使用 demucs 进行人声/背景音分离，保留原 BGM
- 使用段落级 TTS 合成（按 ≥8s 静音分段），减少 API 调用和 atempo 伪影

## Constraints

- **API 依赖**: 必须有硅基流动 API Key — 所有 AI 功能依赖云端 API
- **浏览器环境**: 平台登录需要浏览器环境 — Playwright/Selenium 依赖
- **网络要求**: 需要访问 YouTube 和国内平台 — 可能需要代理

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 使用硅基流动 API 替代本地模型 | 降低部署复杂度，统一 AI 服务 | ✓ Good |
| 使用 Playwright 进行浏览器自动化 | 支持现代 Web 平台登录 | — Pending |
| 使用 APScheduler 进行定时任务 | 轻量级，易于集成 | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-29 — v5.0 开源化深度改造 milestone started (v4.0 deferred)*
