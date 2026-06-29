# VidDub — YouTube 视频中文配音 + 自动发布工具

> 自动把 YouTube 英文视频转成中文配音视频，并一键发布到西瓜视频 / 哔哩哔哩。
> v2.0 端到端管线：URL → 下载 → Whisper STT → SiliconFlow 翻译 → CosyVoice2 TTS → ffmpeg 合成 → AI 标题 → 自动发布。

---

## 功能列表

按 Phase 顺序：

| Phase | 主要功能 |
|-------|----------|
| 1 | 项目骨架（FastAPI + Vue 3 + Element Plus + 数据库模型 + WebSocket） |
| 2 | YouTube 搜索 / 频道扫描 / yt-dlp 下载 / 任务队列 |
| 3 | 字幕模型 + 字幕编辑界面 |
| 4 | **核心翻译配音管线**：URL → 中文配音 mp4（CLI + REST API + 6 步管线） |
| 5 | Web UI 改造：任务列表、配音预览、5-tab 配置页、字幕编辑、Dashboard |
| 6 | 平台自动登录：Playwright 扫码西瓜/哔哩哔哩 + 登录态持久化 |
| 7 | 平台自动发布：标题/标签/封面自动填充 + 进度监控 + 发布历史 |
| 8 | AI 智能标题与标签：SiliconFlow Chat JSON mode 生成 5 候选标题 + 8 标签 |
| 9 | 定时任务 + 批量管理：APScheduler 频道扫描 + 批量操作 + CSV/JSON 导出 |
| 10 | 部署脚本（setup/start）+ 完整文档 + 集成 smoke test |

---

## 系统要求

| 项 | 要求 |
|----|------|
| 操作系统 | Windows 10/11、Ubuntu 20.04+、macOS 12+ |
| Python | **3.10+**（推荐 3.11/3.12） |
| Node.js | **18+**（推荐 20 LTS） |
| ffmpeg | 任意现代版本，必须在 PATH 中 |
| yt-dlp | 由 pip 自动安装，也可独立装到 PATH |
| 网络 | 必须能访问 YouTube + SiliconFlow API（`https://api.siliconflow.cn`） |
| GPU | 可选（Whisper CPU 即可运行；GPU 加速需 CUDA） |
| 磁盘 | ≥ 5 GB（含 Whisper 模型 + Playwright Chromium + node_modules） |

---

## 快速开始（3 步）

### 第 1 步：环境初始化

**Windows（PowerShell）：**
```powershell
PS> .\setup.ps1
```

**Linux / macOS：**
```bash
$ chmod +x setup.sh start.sh
$ ./setup.sh
```

脚本会自动：
- 检查 Python / Node / ffmpeg / yt-dlp 依赖
- 创建 `backend/venv/`
- 安装后端 Python 依赖 + Playwright Chromium + Whisper tiny 模型
- 安装前端 npm 依赖
- 运行数据库迁移（Alembic）
- 从 `.env.example` 复制创建 `backend/.env`

### 第 2 步：配置 API Key

编辑 `backend/.env`：

```dotenv
SILICONFLOW_API_KEY=sk_your_real_key_here
```

申请地址：https://cloud.siliconflow.cn/account/ak

完整配置项说明见 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

### 第 3 步：启动服务

**Windows：**
```powershell
PS> .\start.ps1
```

**Linux / macOS：**
```bash
$ ./start.sh
```

启动后访问：
- **前端 Web UI**：http://localhost:5173
- **后端 API Swagger 文档**：http://localhost:8000/docs
- **后端 API ReDoc**：http://localhost:8000/redoc

---

## 目录结构

```
viddub/
├── backend/
│   ├── alembic/              # 数据库迁移
│   │   └── versions/         # 各 Phase 迁移脚本
│   ├── app/
│   │   ├── api/              # FastAPI 路由 (18 个模块)
│   │   ├── core/             # 配置、数据库、WebSocket
│   │   ├── models/           # SQLAlchemy ORM 模型
│   │   ├── services/         # 业务逻辑
│   │   │   ├── siliconflow/  # SiliconFlow API 封装 (client/translate/tts)
│   │   │   ├── dubbing/      # ffmpeg 编排层 (pipeline/alignment/...)
│   │   │   ├── platform/     # 平台登录 (bilibili/ixigua)
│   │   │   ├── publish/      # 平台发布 (base/bilibili/ixigua/manager)
│   │   │   ├── title_generator.py     # AI 标题
│   │   │   ├── channel_scanner.py     # 定时扫描
│   │   │   ├── scheduler.py           # 任务调度核心
│   │   │   ├── whisper_service.py     # 本地 Whisper
│   │   │   └── youtube.py             # yt-dlp 封装
│   │   ├── cli.py            # 命令行入口 (dub/status/resume)
│   │   ├── main.py           # FastAPI app
│   │   └── uploader.py       # Bilibili 上传 SDK (旧)
│   ├── data/                 # SQLite + storage_state (gitignored)
│   ├── downloads/            # 视频成品 (gitignored)
│   ├── tests/                # pytest 单元 + 集成测试 (222+1)
│   ├── requirements.txt
│   ├── pytest.ini
│   └── .env / .env.example
├── frontend/
│   ├── src/
│   │   ├── api/              # axios + TS 类型定义
│   │   ├── views/            # 页面组件 (Tasks/Dashboard/Settings/Platform/Publish/Channels/Subtitle)
│   │   ├── components/       # 通用组件 (AiTitleSelector/AudioPreview/DubCreateDialog)
│   │   ├── stores/           # Pinia (taskStore/wsStore)
│   │   ├── layouts/          # MainLayout
│   │   └── router/           # vue-router
│   ├── package.json
│   └── vite.config.ts
├── docs/                     # 文档 (本目录)
├── setup.ps1 / setup.sh      # 一键环境初始化
├── start.ps1 / start.sh      # 一键启动
├── README.md                 # 本文件
├── CHANGELOG.md              # 版本变更日志
└── .planning/                # 项目规划文档 (PROJECT/ROADMAP/STATE/REQUIREMENTS + 各 Phase SUMMARY)
```

---

## 配置说明

- **必填**：`SILICONFLOW_API_KEY`（在 `backend/.env`）
- **应用配置**：所有运行时可调参数存在 `app_config` 表（首次启动 seed 默认值），可在 Web UI `/settings` 页面修改
- **完整列表**：[docs/CONFIGURATION.md](docs/CONFIGURATION.md)

---

## 常见问题

请参考 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。

涵盖：API Key 错误、SiliconFlow 限流、Whisper 模型下载、ffmpeg 缺失、Playwright 启动失败、Windows 路径问题、SQLite 锁、平台风控等。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Python 3.10+ / FastAPI 0.115 / uvicorn |
| ORM | SQLAlchemy 2.0 async + aiosqlite |
| 数据库 | SQLite（WAL 模式） |
| 迁移 | Alembic 1.13 |
| 任务调度 | APScheduler 3.10（定时扫描）+ 自研 TaskScheduler（配音 chain） |
| 视频下载 | yt-dlp |
| 语音识别 (STT) | 本地 Whisper (tiny/base/small/medium) |
| 翻译 | SiliconFlow Chat API (Qwen2.5-7B-Instruct) |
| 语音合成 (TTS) | SiliconFlow API (FunAudioLLM/CosyVoice2-0.5B) |
| 浏览器自动化 | Playwright (平台登录/发布) + qrcode (哔哩哔哩 HTTP QR) |
| 视频/音频处理 | ffmpeg (extract/atempo/amix/compose) |
| 前端框架 | Vue 3.5 / Vite 5 / TypeScript 5 / Pinia 2 |
| UI 库 | Element Plus 2.9 + @element-plus/icons-vue |
| 图表 | ECharts 5 / vue-echarts 7 |
| HTTP | axios 1.7 (前端) + httpx 0.28 (后端) |
| 测试 | pytest 8 + pytest-asyncio + pytest-mock |

---

## 开发者文档

| 主题 | 文件 |
|------|------|
| 架构与数据流 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| API 端点速览 | [docs/API.md](docs/API.md) |
| 配置项完整说明 | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| 常见问题排查 | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| 生产部署指南 | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| 版本变更日志 | [CHANGELOG.md](CHANGELOG.md) |
| 项目规划 | `.planning/PROJECT.md` / `.planning/ROADMAP.md` |
| 各 Phase 交付记录 | `.planning/phases/*/0*-SUMMARY.md` |

### 开发模式

```bash
# 后端热重载
cd backend
venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# 或 Linux: venv/bin/uvicorn ...

# 前端热重载
cd frontend
npm run dev

# 跑测试
cd backend
venv\Scripts\python -m pytest tests/ -v

# 前端构建
cd frontend
npm run build
```

---

## License

MIT License. 见 [LICENSE](LICENSE)（如未单独创建，则默认 MIT）。

本项目仅供个人学习使用。使用者需自行承担因使用本工具产生的法律责任。请遵守 YouTube / 西瓜视频 / 哔哩哔哩 的服务条款，尊重视频原作者的版权。

---

*文档版本：v2.0 (Phase 10) · 最后更新：2026-06-22*
