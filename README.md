<div align="center">

# VidDub

**YouTube 视频中文配音 + 多平台自动发布**

[![GitHub Stars](https://img.shields.io/github/stars/yaoyue123/VidDub?style=flat-square&logo=github)](https://github.com/yaoyue123/VidDub/stargazers)
[![License](https://img.shields.io/github/license/yaoyue123/VidDub?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Vue.js](https://img.shields.io/badge/Vue-3.5-4FC08D?style=flat-square&logo=vue.js)](https://vuejs.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square)](CONTRIBUTING.md)

[**简体中文**](README.md) | [**English**](README_EN.md)

> 自动把 YouTube 英文视频转成中文配音视频，并一键发布到 Bilibili / Douyin / Kuaishou / Tencent Video / Xiaohongshu。
> **v5.3** 端到端管线：YouTube URL → Whisper STT → 多引擎翻译（Google / SiliconFlow）→ 多引擎 TTS（MOSS 本地 / Edge / CosyVoice2）→ ffmpeg 合成 → 双语字幕 → 多平台自动发布。

---

</div>

## 📋 目录

- [项目简介](#-项目简介)
- [功能特性](#-功能特性)
- [系统要求](#-系统要求)
- [快速开始](#-快速开始)
- [API 配置](#-api-配置)
- [CLI 命令行](#-cli-命令行)
- [Docker 部署](#-docker-部署)
- [目录结构](#-目录结构)
- [技术栈](#-技术栈)
- [开发文档](#-开发文档)
- [开发模式](#-开发模式)
- [参与贡献](#-参与贡献)
- [许可证与免责](#-许可证与免责)
- [Star 历史](#-star-历史)

---

## 🌟 项目简介

**VidDub** 是一套完整的端到端视频处理管线，能够：

1. 📥 **下载** — 通过 `yt-dlp` 下载 YouTube 视频（音频 + 视频）
2. 🎙️ **转写** — 使用本地 **Whisper** 将英文语音转为带时间戳的字幕
3. 🌐 **翻译** — 通过 **SiliconFlow AI**（Qwen2.5 / DeepSeek）将英文字幕翻译为中文
4. 🗣️ **配音** — 使用 **MOSS-TTS-Nano（本地）/ Edge-TTS / CosyVoice2** 合成中文语音
5. 🎬 **合成** — 用 `ffmpeg` 替换原始音轨，生成高质量中文配音视频
6. 🤖 **智能标题** — AI 自动生成 5 个标题候选 + 8 个标签
7. 📤 **发布** — 一键发布到 **5 个主流中文视频平台**

无论你是希望拓展中文市场的内容创作者，还是探索 AI 视频处理的开发者，VidDub 都提供了一个完整、生产就绪的解决方案。

---

## ✨ 功能特性

| 步骤 | 技术 | 说明 |
|------|------|------|
| 1️⃣ 📥 视频下载 | `yt-dlp` | 下载 YouTube 视频（音频 + 视频流） |
| 2️⃣ 🎙️ 语音转文字 | **Whisper**（本地） | 生成带单词级时间戳的源语言字幕 |
| 3️⃣ 🌐 智能翻译 | **Google / SiliconFlow** | 英文→中文翻译；Google 免费无需 Key，SiliconFlow 提供 LLM 上下文翻译 |
| 4️⃣ 🗣️ 语音合成 | **MOSS-TTS-Nano / Edge-TTS / CosyVoice2** | MOSS 本地离线（0.1B，中文内置音色）、Edge 在线免费、CosyVoice2 云端高质量 |
| 5️⃣ 🎬 音频处理 | `ffmpeg` | 速度对齐、混音、替换音轨 |
| 6️⃣ 🤖 AI 标题 | **SiliconFlow JSON 模式** | 每视频生成 5 个标题候选 + 8 个标签 |
| 7️⃣ 📤 自动发布 | **social-auto-upload** | 一键发布到 Bilibili、抖音、快手、腾讯视频、小红书 |

### 为什么选择 VidDub？

| 特性 | 说明 |
|------|------|
| 🎯 **生产就绪** | 从 YouTube URL 到发布的完整端到端管线 |
| 🔊 **多引擎配音** | MOSS 本地离线、Edge 免费在线、CosyVoice2 云端高质量，支持声音克隆 |
| 🌍 **多平台发布** | 覆盖 5 个主流中文视频平台 |
| 🤖 **AI 驱动** | 上下文感知翻译、AI 标题生成、智能标签 |
| 💻 **全栈覆盖** | Web UI + CLI 命令行 + REST API，任你选择 |
| 🐳 **Docker 支持** | Docker Compose 一键部署 |
| 📊 **数据分析** | 内容看板与效果追踪 |

---

## 📋 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10/11, Ubuntu 20.04+, macOS 12+ |
| Python | **3.10+**（推荐 3.11/3.12） |
| Node.js | **18+**（推荐 20 LTS） |
| ffmpeg | 任意现代版本，需在 PATH 中 |
| yt-dlp | pip 自动安装 |
| 网络 | 需能访问 YouTube；本地 MOSS + Whisper 可离线运行（模型首次下载需联网）；云端后端需访问 SiliconFlow / Google |
| GPU | 可选（Whisper 可在 CPU 运行；CUDA 可加速） |
| 磁盘 | >= 5 GB（Whisper 模型 + Playwright Chromium + node_modules） |

---

## 🚀 快速开始

### 第一步：一键启动

```powershell
# Windows
PS> .\start.bat

# Linux / macOS
$ chmod +x start.sh
$ ./start.sh
```

启动脚本自动完成以下操作：
- ✅ 初始化 `social-auto-upload` submodule（发布后端）
- ✅ 检查 / 自动安装 **uv**（Rust 编写的极速 Python 包管理器）
- ✅ `uv sync` 创建 `.venv` + 安装所有 Python 依赖
- ✅ 安装 Playwright Chromium
- ✅ 安装前端 npm 依赖
- ✅ 执行数据库迁移（Alembic）
- ✅ 复制 `.env.example` 到 `backend/.env`
- ✅ 启动后端 + 前端服务

> 手动克隆后如果没跑启动脚本，请先执行一次：
> `git submodule update --init --recursive`

### 第二步：选择配音/翻译后端

**完全免费 + 本地离线**（推荐，无需 API Key）：在 Web UI → 设置中改为

```
翻译后端 = google
配音后端 = moss
默认音色 = Junhao
```

首次使用 MOSS 前安装本地模型（约 500MB，脚本会创建独立 venv）：

```powershell
powershell -ExecutionPolicy Bypass -File backend\scripts\install_moss_tts.ps1 -DownloadModels
```

**云端高质量**：编辑 `backend/.env`

```dotenv
SILICONFLOW_API_KEY=sk_your_real_key_here
```

申请密钥：https://cloud.siliconflow.cn/account/ak ，然后在设置中选择 `siliconflow` 后端。

> 完整配置参考见 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

启动后访问：
- ✨ **前端 Web UI：** http://localhost:5173
- 📖 **后端 API Swagger：** http://localhost:8000/docs
- 📖 **后端 API ReDoc：** http://localhost:8000/redoc

---

## 🔑 API 配置

VidDub 支持**云端**与**本地免费**两类后端，均在 Web UI → 设置或 `/api/config` 中切换。

### 免费 / 本地（无需 API Key）

| 服务 | 后端 | 说明 |
|------|------|------|
| 翻译 | `google` | Google Translate 免费接口，无需 Key |
| TTS | `moss` | MOSS-TTS-Nano 0.1B，本地 ONNX，中文内置音色 |
| TTS | `edge-tts` | 微软 Edge 免费语音，无需安装；部分网络会被 403 限制 |
| STT | `whisper` | 本地 Whisper 模型（tiny/base/small/medium） |

### 云端 SiliconFlow（可选）

```dotenv
# backend/.env
SILICONFLOW_API_KEY=sk_your_key_here
# SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
```

| 服务 | 可用模型 |
|------|---------|
| 翻译 | Qwen2.5-7B/14B/72B、DeepSeek-V2.5、DeepSeek-V4-Flash |
| TTS | CosyVoice2-0.5B、CosyVoice2 声音克隆 |

模型选择、语速、音色等运行时参数在 `configs` 表中（Web UI 可改），不是 `.env`。
完整清单见 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

---

## 🖥️ CLI 命令行

VidDub 提供强大的命令行工具，适合无头模式运行：

```bash
# 激活虚拟环境
cd backend
venv\Scripts\python -m app.cli --help

# 配音单个 YouTube 视频
venv\Scripts\python -m app.cli dub "https://youtube.com/watch?v=xxx"

# 查看任务状态
venv\Scripts\python -m app.cli status

# 恢复中断的任务
venv\Scripts\python -m app.cli resume
```

---

## 🐳 Docker 部署

```bash
# 构建并启动
docker compose up --build

# 后台运行
docker compose up -d --build
```

Docker 部署说明详见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

---

## 📁 目录结构

```
viddub/
├── backend/                    # Python 后端
│   ├── alembic/                # 数据库迁移
│   │   └── versions/           # 迁移脚本
│   ├── app/
│   │   ├── api/                # FastAPI 路由（16 个模块）
│   │   ├── core/               # 配置、数据库、WebSocket
│   │   ├── models/             # SQLAlchemy ORM 模型
│   │   ├── services/           # 业务逻辑
│   │   │   ├── siliconflow/    # SiliconFlow 云端 API
│   │   │   ├── translator/     # 翻译提供者（google / siliconflow）
│   │   │   ├── tts_new/        # TTS 提供者（moss / edge-tts / siliconflow）
│   │   │   ├── dubbing/        # ffmpeg 编排、对齐、字幕烧录
│   │   │   ├── platforms/      # 平台注册表（5 平台）
│   │   │   ├── platform/       # 平台登录/扫码
│   │   │   ├── publish/        # 平台发布
│   │   │   ├── title_generator.py     # AI 标题生成
│   │   │   ├── channel_scanner.py     # 定时频道扫描
│   │   │   ├── scheduler.py           # 任务调度
│   │   │   ├── whisper_service.py     # 本地 Whisper STT
│   │   │   └── youtube.py             # yt-dlp 封装
│   │   ├── cli.py              # CLI 入口
│   │   └── main.py             # FastAPI 应用
│   ├── scripts/                # 手动工具（install_moss_tts、发布调试）
│   ├── data/                   # SQLite + 本地模型（gitignore）
│   ├── downloads/              # 视频输出（gitignore）
│   ├── tests/                  # pytest 测试
│   ├── pyproject.toml           # uv 项目配置（推荐）
│   ├── requirements.txt         # pip 兼容（传统方式）
│   └── .env / .env.example
├── frontend/                   # Vue 3 前端
│   ├── src/
│   │   ├── api/                # axios HTTP 客户端
│   │   ├── views/              # 页面组件
│   │   ├── components/         # 共享组件
│   │   ├── stores/             # Pinia 状态管理
│   │   ├── layouts/            # 布局组件
│   │   └── router/             # vue-router 配置
│   ├── package.json
│   └── vite.config.ts
├── social-auto-upload/         # 发布库 submodule（5 平台）
├── docs/                       # 文档
│   ├── ARCHITECTURE.md         # 架构说明
│   ├── API.md                  # API 参考
│   ├── CONFIGURATION.md        # 配置参考
│   ├── DEPLOYMENT.md           # 部署指南
│   ├── TROUBLESHOOTING.md      # 故障排查
│   └── SOCIAL_AUTO_UPLOAD.md   # 发布配置
├── docker-compose.yml          # Docker Compose
├── Dockerfile                  # Docker 多阶段构建
├── .gitmodules                 # social-auto-upload 子模块定义
├── start.bat / start.sh        # 一键启动脚本（含 submodule 初始化）
├── README.md                   # 本文件（中文版）
├── README_EN.md                # 英文版 README
├── LICENSE                     # MIT 许可证
├── CONTRIBUTING.md             # 贡献指南
├── CODE_OF_CONDUCT.md          # 行为准则
├── SECURITY.md                 # 安全策略
└── CHANGELOG.md                # 版本更新日志
```

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| **后端框架** | Python 3.10+ / FastAPI 0.115 / uvicorn |
| **ORM** | SQLAlchemy 2.0 async + aiosqlite |
| **数据库** | SQLite（WAL 模式） |
| **数据库迁移** | Alembic 1.13 |
| **任务调度** | APScheduler 3.10 + 自定义 TaskScheduler |
| **视频下载** | yt-dlp |
| **语音转文字** | 本地 Whisper（tiny / base / small / medium） |
| **翻译引擎** | Google Translate（免费）/ SiliconFlow Chat（Qwen2.5 / DeepSeek-V4-Flash） |
| **语音合成** | MOSS-TTS-Nano 0.1B（本地 ONNX）/ Edge-TTS / CosyVoice2-0.5B |
| **声音克隆** | CosyVoice2 通过 tts_new 提供者模式 |
| **浏览器自动化** | Playwright（平台登录） |
| **发布引擎** | social-auto-upload（5 平台） |
| **视频/音频处理** | ffmpeg（提取 / 变速 / 混音 / 合成） |
| **前端框架** | Vue 3.5 / Vite 5 / TypeScript 5 / Pinia 2 |
| **UI 组件库** | Element Plus 2.9 + @element-plus/icons-vue |
| **图表** | ECharts 5 / vue-echarts 7 |
| **HTTP 客户端** | axios 1.7（前端）+ httpx 0.28（后端） |
| **测试** | pytest 8 + pytest-asyncio + pytest-mock |

---

## 📚 开发文档

| 主题 | 文件 |
|------|------|
| 架构与数据流 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| API 接口参考 | [docs/API.md](docs/API.md) |
| 配置参考 | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| 故障排查 | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| 生产部署 | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| social-auto-upload 配置 | [docs/SOCIAL_AUTO_UPLOAD.md](docs/SOCIAL_AUTO_UPLOAD.md) |
| 版本更新日志 | [CHANGELOG.md](CHANGELOG.md) |
| 贡献指南 | [CONTRIBUTING.md](CONTRIBUTING.md) |

---

## 💻 开发模式

```bash
# 后端热重载（uv 推荐）
cd backend
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 后端热重载（pip/venv）
cd backend
venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 前端热重载
cd frontend
npm run dev

# 运行测试（uv 推荐）
cd backend
uv run python -m pytest tests/ -v

# 运行测试（pip/venv）
cd backend
venv\Scripts\python -m pytest tests/ -v

# 前端生产构建
cd frontend
npm run build
```

---

## 🤝 参与贡献

我们欢迎所有形式的贡献！请查阅 [CONTRIBUTING.md](CONTRIBUTING.md) 了解：

- 开发环境搭建
- 代码风格规范（Black、Ruff、ESLint、Prettier）
- 测试要求
- 分支管理与 PR 流程

所有贡献者请遵守我们的[行为准则](CODE_OF_CONDUCT.md)。

---

## 📄 许可证与免责

**许可证：** MIT License。详见 [LICENSE](LICENSE)。

**免责声明：** 本项目仅供个人学习和研究使用。用户需自行承担以下责任：

- 遵守 YouTube、Bilibili、抖音、快手、腾讯视频、小红书等平台的服务条款
- 尊重原始视频版权和知识产权
- 确保拥有下载、翻译、再发布内容的合法权利
- 遵循所有适用的法律法规

作者不对任何滥用本软件的行为承担责任。

---

## ⭐ Star 历史

[![Star History Chart](https://api.star-history.com/svg?repos=yaoyue123/VidDub&type=Timeline)](https://star-history.com/#yaoyue123/VidDub&Timeline)

---

<div align="center">

**如果你觉得 VidDub 对你有帮助，请在 GitHub 上给我们一个 ⭐！**

*文档版本：v5.3 · 最后更新：2026-11-24*

</div>
