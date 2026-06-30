# VidDub 知识库

**生成:** 2026-06-30
**提交:** 997b813
**分支:** master

## 概览

YouTube 视频中文配音 + 多平台自动发布。后端 Python/FastAPI + 前端 Vue 3/TypeScript。端到端管线：下载→STT→翻译→TTS→合成→发布。

## 目录结构

```
VidDub/
├── backend/          # Python FastAPI 后端（129 文件）
│   ├── app/
│   │   ├── api/      # 17 个路由模块（FastAPI）
│   │   ├── core/     # 配置、数据库、WebSocket
│   │   ├── models/   # 12 个 SQLAlchemy ORM 模型
│   │   ├── services/ # 业务逻辑（调度、配音、发布等）
│   │   ├── cli.py    # CLI 入口（dub/status/resume）
│   │   └── main.py   # FastAPI 应用入口
│   └── tests/        # pytest 测试
├── frontend/         # Vue 3 + Vite + TypeScript（28 文件）
│   └── src/
│       ├── views/     # 7 个页面组件
│       ├── stores/    # 6 个 Pinia 状态存储
│       └── components/# 共享组件
├── docs/             # 文档（8 篇）
└── social-auto-upload/ # vendored 发布库
```

## 查询指南

| 任务 | 位置 | 说明 |
|------|------|------|
| 新增 API 端点 | `backend/app/api/` | 在 router.py 注册 |
| 修改数据库模型 | `backend/app/models/` | 需同步创建 Alembic 迁移 |
| 修改配音管线 | `backend/app/services/dubbing/` | 管线编排在 scheduler.py |
| 新增发布平台 | `backend/app/services/publish/` | 继承 BasePublisher |
| 新增翻译引擎 | `backend/app/services/siliconflow/` | 或新增 provider |
| 修改前端页面 | `frontend/src/views/` | Vue 3 Composition API |
| 修改状态管理 | `frontend/src/stores/` | Pinia stores |
| 修改配置项 | `backend/app/core/config.py` | 同时更新 docs/CONFIGURATION.md |
| 数据库迁移 | `alembic/versions/` | `alembic revision --autogenerate` |

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

# 后端测试（pip/venv 兼容）
cd backend && venv\Scripts\python -m pytest tests/ -v

# 后端热重载（pip/venv 兼容）
cd backend && venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 注意事项

- Whisper 模型首次运行自动下载（约 1.5GB tiny 模型）
- Playwright Chromium 在 `pip install` 后需手动安装：`playwright install chromium`
- `social-auto-upload/` 为 vendored 库，更新时需同步 `conf.py` 中的 cookie 配置
- Windows 上使用 `start_server.py`（ProactorEventLoop 解决 asyncio subprocess 问题）
- Docker 多阶段构建：`docker compose up --build`
