# Tech Stack

**Generated:** 2026-06-30
**Focus:** tech

## Languages

| Language | Usage | Version |
|----------|-------|---------|
| Python | Backend API + services + CLI | 3.10+ |
| TypeScript | Frontend application | 5.x |
| Vue | Frontend SFC components | 3.5+ |
| CSS | Frontend styling (vanilla + Element Plus theme) | — |
| YAML | Docker Compose configuration | — |
| PowerShell/Bash | Startup and setup scripts | — |

## Runtimes

- **Python runtime**: CPython 3.10+ (3.11/3.12 recommended)
- **Node.js**: 18+ (20 LTS recommended)
- **Database**: SQLite 3 (WAL mode, FTS5 enabled)
- **Container**: Docker + Docker Compose

## Backend Framework

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Web framework | FastAPI | 0.115.0 | REST API + WebSocket |
| ASGI server | uvicorn | 0.30.0 | Async HTTP server |
| ORM | SQLAlchemy | 2.0.35 | Async ORM with aiosqlite |
| Migration | Alembic | 1.13.0 | Schema migrations |
| Config | pydantic-settings | 2.5.0 | Environment + app config |
| WebSocket | websockets | 13.0 | Real-time progress events |
| Auth (multi-part) | python-multipart | 0.0.12 | Form data parsing |

## Frontend Framework

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Framework | Vue | 3.5+ | SPA framework |
| Build tool | Vite | 5.x | Dev server + bundler |
| Language | TypeScript | 5.x | Type-safe JavaScript |
| State management | Pinia | 2.3+ | Stores |
| Router | vue-router | 4.5+ | Client-side routing |
| UI library | Element Plus | 2.9+ | Component library |
| Icons | @element-plus/icons-vue | — | Icon set |
| Charts | ECharts 5 + vue-echarts 7 | — | Analytics dashboards |
| HTTP client | axios | 1.7 | API requests |
| Auto-import | unplugin-auto-import | — | Automatic imports |
| Auto-components | unplugin-vue-components | — | Automatic component registration |

## Core Dependencies

### Python (`backend/requirements.txt`)

| Dependency | Version | Purpose |
|-----------|---------|---------|
| yt-dlp | >=2024.12 | YouTube video download |
| openai-whisper | >=20231117 | Local speech-to-text (tiny/base/small/medium models) |
| openai | >=1.40 | OpenAI-compatible API client |
| httpx | >=0.28.1 | Async HTTP client |
| tenacity | >=8.5 | Retry logic for API calls |
| edge-tts | >=6.1 | Edge TTS fallback |
| playwright | >=1.40 | Browser automation for platform login |
| qrcode | >=7.4 | QR code generation for login |
| APScheduler | >=3.10 | Task scheduling |
| pytest | >=8.0 | Testing framework |
| pytest-asyncio | >=0.23 | Async test support |
| pytest-mock | >=3.12 | Mocking support |

### Node.js (`frontend/package.json`)

| Dependency | Version | Purpose |
|-----------|---------|---------|
| vue | ^3.5.0 | Core framework |
| vue-router | ^4.5.0 | Routing |
| pinia | ^2.3.0 | State management |
| element-plus | ^2.9.0 | Component library |
| echarts | ^5.6.0 | Charts |
| vue-echarts | ^7.0.0 | Vue chart integration |
| axios | ^1.7.0 | HTTP client |
| @element-plus/icons-vue | — | Icon components |

## Build & Dev Tools

| Tool | Purpose | Configuration |
|------|---------|---------------|
| Black | Python formatter | `--line-length 100` |
| Ruff | Python linter | Default rules |
| isort | Python import sorter | `--profile black` |
| ESLint | TypeScript/JS linter | `frontend/.eslintrc` |
| Prettier | TypeScript/Vue formatter | `frontend/.prettierrc` |
| Vite | Frontend bundler | `frontend/vite.config.ts` |
| pytest | Python test runner | `backend/pytest.ini` |
| Docker | Containerization | `Dockerfile` (multi-stage) |
| Docker Compose | Service orchestration | `docker-compose.yml` |

## Infrastructure

- **Container**: Docker multi-stage build (python-base → backend-builder → frontend-builder → runtime)
- **Deployment**: Docker Compose with persistent volumes for data, downloads, config
- **No cloud infrastructure**: Fully self-hosted, single-machine deployment
