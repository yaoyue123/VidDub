<div align="center">

# VidDub

**YouTube Video Chinese Dubbing + Multi-Platform Auto-Publish**

[![GitHub Stars](https://img.shields.io/github/stars/yaoyue123/VidDub?style=flat-square&logo=github)](https://github.com/yaoyue123/VidDub/stargazers)
[![License](https://img.shields.io/github/license/yaoyue123/VidDub?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Vue.js](https://img.shields.io/badge/Vue-3.5-4FC08D?style=flat-square&logo=vue.js)](https://vuejs.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square)](CONTRIBUTING.md)

[**简体中文**](README.md) | [**English**](README_EN.md)

> Automatically convert YouTube English videos into Chinese-dubbed videos and publish them with one click to **Bilibili / Douyin (TikTok) / Kuaishou / Tencent Video / Xiaohongshu (RED)**.

---

</div>

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Demo](#-demo)
- [System Requirements](#-system-requirements)
- [Quick Start](#-quick-start)
- [API Configuration](#-api-configuration)
- [CLI Usage](#-cli-usage)
- [Directory Structure](#-directory-structure)
- [Tech Stack](#-tech-stack)
- [Documentation](#-documentation)
- [Contributing](#-contributing)
- [License & Disclaimer](#-license--disclaimer)
- [Star History](#-star-history)

---

## 🌟 Overview

**VidDub** is an end-to-end pipeline that:

1. Downloads YouTube videos via `yt-dlp`
2. Transcribes English speech to text using **Whisper** (local)
3. Translates English subtitles to Chinese via **SiliconFlow AI** (Qwen2.5 / DeepSeek)
4. Synthesizes natural Chinese speech with **CosyVoice2 TTS**
5. Replaces the original audio track with high-quality Chinese dubbing
6. Generates AI-powered titles and tags
7. Publishes to **5 Chinese video platforms** automatically with one click

Whether you're a content creator looking to expand to the Chinese market, or a developer exploring AI-powered video processing, VidDub provides a complete, production-ready solution.

---

## ✨ Features

| # | Step | Technology | What It Does |
|---|------|-----------|--------------|
| 1 | 📥 Download | `yt-dlp` | Downloads YouTube video (audio + video streams) |
| 2 | 🎙️ Speech-to-Text | **Whisper** (local) | Generates source subtitles with word-level timestamps |
| 3 | 🌐 Translation | **SiliconFlow Chat** (Qwen2.5 / DeepSeek-V4) | Translates English → Chinese with sliding-window context |
| 4 | 🗣️ Text-to-Speech | **CosyVoice2 TTS** via SiliconFlow API | Synthesizes natural Chinese speech per subtitle segment |
| 5 | 🎬 Audio Processing | `ffmpeg` | Speed-aligns, mixes, and replaces the audio track |
| 6 | 🤖 AI Titles | **SiliconFlow JSON mode** | Generates 5 title candidates + 8 tags per video |
| 7 | 📤 Auto-Publish | **social-auto-upload** | One-click publish to Bilibili, Douyin, Kuaishou, Tencent Video, Xiaohongshu |

### Why VidDub?

- **🎯 Production Ready**: End-to-end pipeline from YouTube URL to published video
- **🔊 High Quality Voice**: CosyVoice2 TTS with voice cloning support
- **🌍 Multi-Platform**: Publish to 5 major Chinese video platforms
- **🤖 AI-Powered**: Smart translation with context awareness, AI title generation
- **💻 Full Stack**: Web UI + CLI + REST API — use it your way
- **🐳 Docker Support**: Easy deployment with Docker Compose
- **📊 Dashboard**: Content analytics and performance tracking

---

## 🎥 Demo

> *Screenshots coming soon — check back for visual demos of the pipeline in action!*

| Web UI | Pipeline Dashboard | Content Analytics |
|--------|-------------------|-------------------|
| Vue 3 + Element Plus UI | Real-time task tracking | ECharts-based analytics |

---

## 📋 System Requirements

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

## 🚀 Quick Start

### Step 1: Environment Setup

**Recommended — via uv (automatic Python version + venv management):**

```powershell
# Windows
PS> .\setup.ps1

# Linux / macOS
$ chmod +x setup.sh start.sh
$ ./setup.sh
```

**Traditional — pip + venv (no uv dependency):**
```bash
cd backend
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python -m playwright install chromium
cp .env.example .env
venv\Scripts\python -m alembic upgrade head
cd ../frontend
npm install
```

The setup script automatically:
- Installs **uv** (blazing-fast Rust-based Python package manager) if not found
- Runs `uv sync` to create `.venv` and install all Python dependencies
- Installs Playwright Chromium + Whisper tiny model
- Installs frontend npm dependencies
- Runs database migration (Alembic)
- Copies `.env.example` to `backend/.env`

### Step 2: Configure API Key

Edit `backend/.env`:

```dotenv
SILICONFLOW_API_KEY=sk_your_real_key_here
```

Apply for a key at: https://cloud.siliconflow.cn/account/ak

> Full configuration reference in [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

### Step 3: Start the Service

**Windows:**
```cmd
> start.bat
```

**Linux / macOS:**
```bash
$ ./start.sh
```

After startup, visit:
- **Frontend Web UI:** http://localhost:5173
- **Backend API Swagger:** http://localhost:8000/docs
- **Backend API ReDoc:** http://localhost:8000/redoc

### Docker Deployment

```bash
docker compose up --build
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for production deployment details.

---

## 🔑 API Configuration

VidDub uses [SiliconFlow API](https://cloud.siliconflow.cn/) for translation and TTS. Configuration is managed via `backend/.env`:

```dotenv
# Core API Key
SILICONFLOW_API_KEY=sk_your_key_here

# Translation Settings (optional)
TRANSLATION_MODEL=Qwen/Qwen2.5-7B-Instruct
TRANSLATION_CONTEXT_WINDOW=5

# TTS Settings (optional)
TTS_MODEL=CosyVoice2-0.5B
TTS_VOICE=default
```

### Supported Models

| Service | Available Models |
|---------|-----------------|
| Translation | Qwen2.5-7B/14B/72B, DeepSeek-V2.5, DeepSeek-V4-Flash |
| TTS | CosyVoice2-0.5B, CosyVoice2-voice-cloning |

> You can also use any OpenAI-compatible API by adjusting the `TRANSLATION_API_BASE_URL` setting.

---

## 🖥️ CLI Usage

VidDub comes with a powerful CLI for headless operation:

```bash
# Activate the virtual environment
cd backend
venv\Scripts\python -m app.cli --help

# Dub a single YouTube video
venv\Scripts\python -m app.cli dub "https://youtube.com/watch?v=xxx"

# Check task status
venv\Scripts\python -m app.cli status

# Resume an interrupted task
venv\Scripts\python -m app.cli resume
```

---

## 📁 Directory Structure

```
viddub/
├── backend/
│   ├── alembic/              # Database migrations
│   │   └── versions/         # Migration scripts
│   ├── app/
│   │   ├── api/              # FastAPI routes (20 modules)
│   │   ├── core/             # Config, database, WebSocket
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── services/         # Business logic
│   │   │   ├── siliconflow/  # SiliconFlow API wrapper
│   │   │   ├── tts_new/      # TTS architecture (provider pattern)
│   │   │   ├── dubbing/      # ffmpeg orchestration
│   │   │   ├── platform/     # Platform login (5 platforms)
│   │   │   ├── publish/      # Platform publish
│   │   │   ├── title_generator.py     # AI title generation
│   │   │   ├── channel_scanner.py     # Scheduled scanning
│   │   │   ├── scheduler.py           # Task scheduling
│   │   │   ├── whisper_service.py     # Local Whisper STT
│   │   │   └── youtube.py             # yt-dlp wrapper
│   │   ├── cli.py            # CLI entry points
│   │   └── main.py           # FastAPI application
│   ├── data/                 # SQLite database (gitignored)
│   ├── downloads/            # Video output (gitignored)
│   ├── tests/                # pytest test suite
│   ├── pyproject.toml           # uv project config (recommended)
│   ├── requirements.txt         # pip compatibility (traditional)
│   └── .env / .env.example
├── frontend/
│   ├── src/
│   │   ├── api/              # axios HTTP client
│   │   ├── views/            # Page components
│   │   ├── components/       # Shared components
│   │   ├── stores/           # Pinia state stores
│   │   ├── layouts/          # Layout components
│   │   └── router/           # vue-router configuration
│   ├── package.json
│   └── vite.config.ts
├── social-auto-upload/       # Publishing library (5 platforms)
├── docs/                     # Documentation
├── docker-compose.yml        # Docker Compose configuration
├── Dockerfile                # Multi-stage Docker build
├── setup.ps1 / setup.sh      # One-click environment setup (uv)
├── start.bat / start.sh      # One-click startup scripts
├── README.md                 # Chinese README (default)
├── README_EN.md              # English README
├── LICENSE                   # MIT License
├── CONTRIBUTING.md           # Contribution guide
├── CODE_OF_CONDUCT.md        # Code of conduct
├── SECURITY.md               # Security policy
└── CHANGELOG.md              # Version changelog
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend Framework** | Python 3.10+ / FastAPI 0.115 / uvicorn |
| **ORM** | SQLAlchemy 2.0 async + aiosqlite |
| **Database** | SQLite (WAL mode) |
| **Migrations** | Alembic 1.13 |
| **Task Scheduling** | APScheduler 3.10 + custom TaskScheduler |
| **Video Download** | yt-dlp |
| **Speech-to-Text** | Local Whisper (tiny / base / small / medium) |
| **Translation** | SiliconFlow Chat (Qwen2.5 / DeepSeek-V4-Flash) |
| **Text-to-Speech** | CosyVoice2-0.5B via SiliconFlow API |
| **Voice Cloning** | CosyVoice2 via tts_new provider pattern |
| **Browser Automation** | Playwright (platform login) |
| **Publishing** | social-auto-upload (5 platforms) |
| **Video/Audio** | ffmpeg (extract / atempo / amix / compose) |
| **Frontend** | Vue 3.5 / Vite 5 / TypeScript 5 / Pinia 2 |
| **UI Library** | Element Plus 2.9 + @element-plus/icons-vue |
| **Charts** | ECharts 5 / vue-echarts 7 |
| **HTTP Clients** | axios 1.7 (frontend) + httpx 0.28 (backend) |
| **Testing** | pytest 8 + pytest-asyncio + pytest-mock |

---

## 📚 Documentation

| Topic | File |
|-------|------|
| Architecture & Data Flow | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| API Endpoint Reference | [docs/API.md](docs/API.md) |
| Configuration Reference | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| Troubleshooting | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| Production Deployment | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| social-auto-upload Setup | [docs/SOCIAL_AUTO_UPLOAD.md](docs/SOCIAL_AUTO_UPLOAD.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |

### Development Mode

```bash
# Backend hot-reload (uv)
cd backend
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Backend hot-reload (pip/venv)
cd backend
venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend hot-reload
cd frontend
npm run dev

# Run tests (uv)
cd backend
uv run python -m pytest tests/ -v

# Run tests (pip/venv)
cd backend
venv\Scripts\python -m pytest tests/ -v

# Frontend production build
cd frontend
npm run build
```

---

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development environment setup
- Code style guidelines (Black, Ruff, ESLint, Prettier)
- Testing requirements
- Branching and PR workflow

We also ask all contributors to adhere to our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## 📄 License & Disclaimer

**License:** MIT License. See [LICENSE](LICENSE).

**Disclaimer:** This project is for personal learning and research purposes only. Users are responsible for:

- Complying with the terms of service of YouTube, Bilibili, Douyin, Kuaishou, Tencent Video, and Xiaohongshu
- Respecting original video copyright and intellectual property
- Ensuring they have the necessary rights to download, translate, and republish content
- Using the platform in accordance with all applicable laws and regulations

The authors assume no liability for any misuse of this software.

---

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=yaoyue123/VidDub&type=Timeline)](https://star-history.com/#yaoyue123/VidDub&Timeline)

---

<div align="center">

**If you find VidDub useful, please give us a ⭐ on GitHub!**

*Document version: v5.0 · Last updated: 2026-06-30*

</div>
