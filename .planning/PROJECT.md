# You2Bili - YouTube 视频搬运工具

## What This Is

自动从 YouTube 发现、筛选、翻译、配音、发布优质视频到国内平台（哔哩哔哩、西瓜视频）的智能工具。v4.0 新增智能选题引擎，自动评分和推荐最适合搬运的视频。

## Core Value

- **智能选题** — 五维评分模型（传播潜力/翻译适配/内容质量/市场潜力/制作成本）自动挖掘优质内容
- **全自动流程** — YouTube 发现 → 下载 → 人声分离 → Whisper 转写 → 翻译 → CosyVoice2 TTS → 混音 → 合成 → 多平台发布
- **自定义规则** — 用户定义筛选条件、权重偏好，可视化规则构建，适应个人搬运策略
- **AI 增强** — 硅基流动 API 集成（语音合成、转写、翻译、语音克隆），AI 标题和标签生成
- Web 界面可视化管理和进度监控

## 目标用户

个人用户（自用工具），本地部署

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

## Current Milestone: v4.0 智能选题与内容追踪 (2026-06-25)

**Goal:** 从"被动加工"升级为"主动发现"——自动挖掘 YouTube 上最适合翻译搬运、最能吸引中文观众的优质视频。

**核心能力：**
- **智能评分引擎** — 五维（传播潜力 + 翻译适配 + 内容质量 + 市场潜力 + 制作成本）对每个视频打出综合分
- **自动发现** — 频道推荐、趋势抓取、关键词挖掘，持续发现新内容源
- **自定义规则** — 用户定义筛选条件、权重偏好、白名单/黑名单，可视化规则构建
- **内容追踪** — 追踪频道更新、评分趋势、搬运效果，仪表盘集中展示

**Target phases:**
- Phase 13: 选题评分引擎（五维模型 + 批量评分）
- Phase 14: 智能发现引擎（频道推荐 + 趋势抓取 + 去重）
- Phase 15: 自定义规则引擎（可视化规则构建 + 权重调整 + 模板）
- Phase 16: 内容追踪仪表盘（推荐列表 + 频道面板 + 一键搬运）
- Phase 17: 数据分析与优化（效果追踪 + 评分反馈 + 月度报告）

**Pivot 背景:**
v2.0-v3.0 完成了"怎么搬"（端到端翻译配音管线 + 平台发布 + UX）。现在的问题是"搬什么"——需要一套系统化的内容筛选和发现机制来替代人工判断。

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

### Active

<!-- Current scope. Building toward these. -->

- [ ] 五维内容评分引擎（传播潜力/翻译适配/内容质量/市场潜力/制作成本）
- [ ] 智能发现引擎（频道推荐/趋势抓取/关键词挖掘/去重）
- [ ] 自定义规则引擎（可视化条件组合/权重调整/预设模板）
- [ ] 内容追踪仪表盘（推荐列表/频道面板/一键搬运）
- [ ] 搬运效果数据分析与评分反馈优化

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- 本地模型（Ollama/LM Studio）— 全部使用硅基流动云端 API
- 多用户系统 — 个人自用工具
- 移动端 App — 仅 Web 界面

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
*Last updated: 2026-06-25 — v4.0 智能选题与内容追踪 milestone started*
