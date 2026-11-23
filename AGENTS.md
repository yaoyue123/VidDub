# VidDub 知识库

**生成:** 2026-11-24
**基线提交:** 69a374c（v5.3 改动见 CHANGELOG）
**分支:** master

## 概览

YouTube 视频中文配音 + 多平台自动发布。后端 Python/FastAPI + 前端 Vue 3/TypeScript。端到端管线：下载→STT→翻译→TTS→合成→字幕→发布。

翻译支持 Google（免费）/ SiliconFlow；TTS 支持 MOSS-TTS-Nano（本地 ONNX）/ Edge-TTS / CosyVoice2；STT 使用本地 Whisper。发布依赖 `social-auto-upload` **submodule**（首次克隆需 `git submodule update --init --recursive`）。

## 目录结构

```
VidDub/
├── backend/          # Python FastAPI 后端（app 101 / tests 30 个 .py）
│   ├── app/
│   │   ├── api/      # 16 个路由模块（FastAPI）
│   │   ├── core/     # 配置、数据库、存储、WebSocket
│   │   ├── models/   # 11 个 SQLAlchemy ORM 模型
│   │   ├── services/ # 业务逻辑（调度、配音、翻译、TTS、发布等）
│   │   ├── cli.py    # CLI 入口（dub/status/resume）
│   │   └── main.py   # FastAPI 应用入口
│   ├── alembic/      # 数据库迁移脚本
│   └── tests/        # pytest 测试
├── frontend/         # Vue 3 + Vite + TypeScript（26 文件）
│   └── src/
│       ├── views/     # 7 个页面组件
│       ├── stores/    # 6 个 Pinia 状态存储
│       └── components/# 4 个共享组件
├── docs/             # 文档（9 篇）
└── social-auto-upload/ # vendored 发布库
```

## 查询指南

| 任务 | 位置 | 说明 |
|------|------|------|
| 新增 API 端点 | `backend/app/api/` | 在 router.py 注册 |
| 修改数据库模型 | `backend/app/models/` | 需同步创建 Alembic 迁移 |
| 修改配音管线 | `backend/app/services/dubbing/pipeline.py` | 6 步管线；任务级调度在 `services/scheduler.py` |
| 新增发布平台 | `backend/app/services/publish/` | 继承 `PlatformPublisher`，在 `platforms/registry.py` 注册描述符 |
| 新增翻译引擎 | `backend/app/services/translator/` | 继承 `TranslationProvider`，在 service.py 按配置选择 |
| 新增 TTS 引擎 | `backend/app/services/tts_new/` | 继承 `TTSProvider`，在 service.py 按配置选择（moss/edge-tts/siliconflow） |
| 本地 TTS 模型 | `backend/data/models/MOSS-TTS-Nano/` | `scripts/install_moss_tts.ps1` 安装；独立 venv，勿与后端 torch 混用 |
| 修改前端页面 | `frontend/src/views/` | Vue 3 Composition API |
| 修改状态管理 | `frontend/src/stores/` | Pinia stores |
| 修改配置项 | `backend/app/core/config.py` | 同时更新 docs/CONFIGURATION.md |
| 数据库迁移 | `backend/alembic/versions/` | `alembic revision --autogenerate` |

## 约定

- **Python**: Black（行宽 100）+ Ruff + isort（profile=black）。类型标注对公共函数必选。
- **TypeScript/Vue**: Composition API + `<script setup lang="ts">`。Prettier + ESLint。
- **提交信息**: 中文，简要描述变更。**禁止 Co-Authored-By trailer**（所有提交均视为单人作者）。
- **分支**: `master`。功能分支命名 `feat/xxx` 或 `fix/xxx`。
- **Import**: 绝对导入优先。`app.api.xxx` 而非相对导入。
- **API**: RESTful，路径 `/api/xxx`。响应统一 `{"data": ...}` 或 `{"detail": "..."}`。

## 反模式（本项目禁止）

- **禁止 Co-Authored-By**: 任何 commit 不得添加 `Co-Authored-By` trailer。本项目所有提交均为单人作者。
- **禁止 `as any` / `@ts-ignore`**: TypeScript 严格模式，类型错误必须修复而非压制。
- **禁止空 `catch`**: `except: pass` / `catch {}` 不允许。
- **禁止硬编码密钥**: 所有密钥通过环境变量注入，不得出现在代码或配置中。
- **禁止删除测试**: 测试失败应修复代码，而非删除测试。
- **禁止 shotgun debug**: 每次修改前必须有根因分析。

## 命令

```bash
# 后端测试（uv 推荐）
cd backend && uv run python -m pytest tests/ -v

# 后端热重载（uv 推荐）
cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 前端热重载
cd frontend && npm run dev

# 前端构建
cd frontend && npm run build

# Python 格式化（uv 推荐）
cd backend && uv run black . --line-length 100 && uv run isort . --profile black

# 数据库迁移（uv 推荐）
cd backend && uv run alembic upgrade head

# 初始化发布 submodule（首次克隆）
git submodule update --init --recursive

# 安装本地 MOSS-TTS（可选，独立 venv）
cd backend && powershell -ExecutionPolicy Bypass -File scripts\install_moss_tts.ps1 -DownloadModels

# 后端测试（pip/venv 兼容）
cd backend && venv\Scripts\python -m pytest tests/ -v

# 后端热重载（pip/venv 兼容）
cd backend && venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 注意事项

- Whisper 模型首次运行自动下载（tiny/base/small/medium）
- `social-auto-upload/` 是 submodule；空目录时先 `git submodule update --init --recursive`
- MOSS-TTS-Nano 首次合成自动下载约 500MB ONNX 权重；8B 版本需 ≥8GB 显存，6GB 显卡用 Nano
- ffmpeg 需在 PATH；字幕烧录依赖 libass（Gyan.FFmpeg full build 已包含）
- Playwright Chromium 在 `pip install` 后需手动安装：`playwright install chromium`
- Windows 上使用 `start_server.py`（ProactorEventLoop 解决 asyncio subprocess 问题）
- Docker 多阶段构建：`docker compose up --build`
