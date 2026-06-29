# You2Bili — YouTube 视频中文配音 + 多平台自动发布

> 自动把 YouTube 英文视频转成中文配音视频，并一键发布到 Bilibili / Douyin / Kuaishou / Tencent Video / Xiaohongshu。
> **v5.0** 端到端管线：YouTube URL 下载 -> Whisper STT -> SiliconFlow 翻译 -> CosyVoice2 TTS -> ffmpeg 合成 -> 字幕 -> 多平台自动发布。

---

## Features

| Step | Technology | Description |
|------|-----------|-------------|
| 1 | yt-dlp | Download YouTube video (audio + video) |
| 2 | Whisper (local) | Speech-to-text, generate source subtitles with timestamps |
| 3 | SiliconFlow Chat (Qwen2.5) | Translate English subtitles to Chinese |
| 4 | CosyVoice2 TTS | Synthesize Chinese speech per segment |
| 5 | ffmpeg | Speed-align, mix, and replace audio track |
| 6 | AI Title Generator | SiliconFlow JSON mode: 5 title candidates + 8 tags |
| 7 | social-auto-upload | Auto-publish to 5 Chinese video platforms |

---

## System Requirements

| Item | Requirement |
|------|-------------|
| OS | Windows 10/11, Ubuntu 20.04+, macOS 12+ |
| Python | **3.10+** (3.11/3.12 recommended) |
| Node.js | **18+** (20 LTS recommended) |
| ffmpeg | Any modern version, must be in PATH |
| yt-dlp | Installed automatically by pip |
| Network | Must reach YouTube + SiliconFlow API (`https://api.siliconflow.cn`) |
| GPU | Optional (Whisper runs on CPU; CUDA for acceleration) |
| Disk | >= 5 GB (Whisper model + Playwright Chromium + node_modules) |

---

## Quick Start (3 Steps)

### Step 1: Environment Setup

**Windows (PowerShell):**
```powershell
PS> .\setup.ps1
```

**Linux / macOS:**
```bash
$ chmod +x setup.sh start.sh
$ ./setup.sh
```

The script automatically:
- Checks Python / Node / ffmpeg / yt-dlp dependencies
- Creates `backend/venv/`
- Installs Python dependencies + Playwright Chromium + Whisper tiny model
- Installs frontend npm dependencies
- Runs database migration (Alembic)
- Copies `.env.example` to `backend/.env`

### Step 2: Configure API Key

Edit `backend/.env`:

```dotenv
SILICONFLOW_API_KEY=sk_your_real_key_here
```

Apply at: https://cloud.siliconflow.cn/account/ak

Full configuration reference in [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

### Step 3: Start the Service

**Windows:**
```powershell
PS> .\start.ps1
```

**Linux / macOS:**
```bash
$ ./start.sh
```

After startup, visit:
- **Frontend Web UI:** http://localhost:5173
- **Backend API Swagger:** http://localhost:8000/docs
- **Backend API ReDoc:** http://localhost:8000/redoc

---

## Directory Structure

```
you2bili/
├── backend/
│   ├── alembic/              # Database migrations
│   │   └── versions/         # Migration scripts per phase
│   ├── app/
│   │   ├── api/              # FastAPI routes (20 modules)
│   │   ├── core/             # Config, database, WebSocket
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── services/         # Business logic
│   │   │   ├── siliconflow/  # SiliconFlow API wrapper (client/translate/tts)
│   │   │   ├── tts_new/      # New TTS architecture (provider pattern)
│   │   │   ├── dubbing/      # ffmpeg orchestration (pipeline/alignment/...)
│   │   │   ├── platform/     # Platform login (5 platforms)
│   │   │   ├── publish/      # Platform publish (5 platforms via social-auto-upload)
│   │   │   ├── title_generator.py     # AI title generation
│   │   │   ├── channel_scanner.py     # Scheduled scanning
│   │   │   ├── scheduler.py           # Task scheduling core
│   │   │   ├── whisper_service.py     # Local Whisper STT
│   │   │   └── youtube.py             # yt-dlp wrapper
│   │   ├── cli.py            # CLI entry points (dub/status/resume)
│   │   └── main.py           # FastAPI app
│   ├── data/                 # SQLite + storage_state (gitignored)
│   ├── downloads/            # Video output (gitignored)
│   ├── tests/                # pytest unit + integration tests
│   ├── requirements.txt
│   ├── pytest.ini
│   └── .env / .env.example
├── frontend/
│   ├── src/
│   │   ├── api/              # axios + TypeScript types
│   │   ├── views/            # Page components
│   │   ├── components/       # Shared components
│   │   ├── stores/           # Pinia stores
│   │   ├── layouts/          # Layout components
│   │   └── router/           # vue-router config
│   ├── package.json
│   └── vite.config.ts
├── social-auto-upload/       # Vendored publishing library (5 platforms)
├── docs/                     # Documentation
├── docker-compose.yml        # Docker deployment
├── Dockerfile                # Docker image build
├── setup.ps1 / setup.sh      # One-click environment setup
├── start.ps1 / start.sh      # One-click startup
├── README.md                 # This file
├── LICENSE                   # MIT License
├── CONTRIBUTING.md           # Contribution guide
└── CHANGELOG.md              # Version changelog
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend Framework | Python 3.10+ / FastAPI 0.115 / uvicorn |
| ORM | SQLAlchemy 2.0 async + aiosqlite |
| Database | SQLite (WAL mode) |
| Migrations | Alembic 1.13 |
| Task Scheduling | APScheduler 3.10 + custom TaskScheduler |
| Video Download | yt-dlp |
| Speech-to-Text | Local Whisper (tiny/base/small/medium) |
| Translation | SiliconFlow Chat (Qwen2.5/DeepSeek-V4-Flash) |
| Text-to-Speech | CosyVoice2-0.5B via SiliconFlow API |
| Voice Cloning | CosyVoice2 via tts_new provider pattern |
| Browser Automation | Playwright (platform login) |
| Publish Backend | social-auto-upload (5 platforms) |
| Video/Audio | ffmpeg (extract/atempo/amix/compose) |
| Frontend | Vue 3.5 / Vite 5 / TypeScript 5 / Pinia 2 |
| UI Library | Element Plus 2.9 + @element-plus/icons-vue |
| Charts | ECharts 5 / vue-echarts 7 |
| HTTP | axios 1.7 (frontend) + httpx 0.28 (backend) |
| Testing | pytest 8 + pytest-asyncio + pytest-mock |

---

## Developer Documentation

| Topic | File |
|-------|------|
| Architecture & Data Flow | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| API Endpoint Reference | [docs/API.md](docs/API.md) |
| Configuration Reference | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| Troubleshooting | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| Production Deployment | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |
| social-auto-upload Setup | [docs/SOCIAL_AUTO_UPLOAD.md](docs/SOCIAL_AUTO_UPLOAD.md) |

### Development Mode

```bash
# Backend hot-reload
cd backend
venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend hot-reload
cd frontend
npm run dev

# Run tests
cd backend
venv\Scripts\python -m pytest tests/ -v

# Frontend build
cd frontend
npm run build
```

---

## License

MIT License. See [LICENSE](LICENSE).

This project is for personal learning and research purposes only. Users are responsible for complying with the terms of service of YouTube, Bilibili, Douyin, Kuaishou, Tencent Video, and Xiaohongshu. Respect original video copyright.

---

*Document version: v5.0 (Phase 6) · Last updated: 2026-06-29*
