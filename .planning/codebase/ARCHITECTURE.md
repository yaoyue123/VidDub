# Architecture

**Generated:** 2026-06-30
**Focus:** arch

## Architectural Pattern

**Pipeline + Orchestrator.** The system follows a linear processing pipeline (7 steps) driven by a central `TaskScheduler` that polls for pending tasks and dispatches to typed handlers. The frontend communicates via REST API + WebSocket for real-time progress.

```
User → API/CLI → TaskScheduler → [Download → STT → Translate → TTS → Compose → Title → Publish]
                              ↘ WebSocket → Frontend UI
```

## System Layers

### 1. API Layer (`backend/app/api/`)
17 route modules registered in `backend/app/api/router.py`:

| Module | File | Purpose |
|--------|------|---------|
| videos | `videos.py` | Video CRUD, listing, search |
| tasks | `tasks.py` | Task management, progress queries |
| config | `config.py` | App configuration CRUD |
| stats | `stats.py` | Dashboard statistics |
| discovery | `discovery.py` | Content discovery |
| subtitles | `subtitles.py` | Subtitle editing |
| transcription | `transcription.py` | STT endpoint |
| tts | `tts.py` | TTS preview endpoint |
| voice_clone | `voice_clone.py` | Voice cloning |
| dub | `dub.py` | Start dubbing pipeline |
| platform | `platform.py` | Platform login status |
| publish | `publish.py` | Publish management |
| title | `title.py` | AI title generation |
| channels | `channels.py` | Channel scanning |
| export | `export.py` | Data export |
| router | `router.py` | Route registration |

All routes follow RESTful `/api/{resource}` pattern. Responses use `{"data": ...}` for success and `{"detail": "..."}` for errors.

### 2. Service Layer (`backend/app/services/`)

**Core Orchestrator:** `scheduler.py` — `TaskScheduler` class
- Polls `tasks` table for pending tasks every N seconds
- Dispatches to typed handlers via `HANDLERS` dict
- Handlers: `_handle_download`, `_handle_transcribe`, `_handle_translate`, `_handle_synthesize`, `_handle_compose`, `_handle_publish`, `_handle_generate_title`
- Concurrent task limit via `asyncio.Semaphore`

**Dubbing Pipeline** (`services/dubbing/`):
- `pipeline.py` — High-level orchestration
- `ffmpeg.py` — ffmpeg command builder (extract audio, atempo, amix, compose)
- `alignment.py` — Audio speed alignment
- `stitcher.py` — Segment concatenation
- `composer.py` — Final video composition with optional background music
- `subtitle_burn.py` — Burn subtitles into video
- `voice_cloner.py` — Voice cloning orchestration
- `audio_separation.py` — BGM separation (Demucs)

**Provider Pattern** (new TTS architecture):
- `tts_new/base.py` — `BaseTTSProvider` abstract class
- `tts_new/siliconflow_provider.py` — SiliconFlow CosyVoice2 implementation
- `tts_new/service.py` — `TTSService` orchestration (segmentation, concurrency, retry)

**Platform Integration:**
- `platform/` — Login managers per platform (bilibili, douyin, kuaishou, tencent, xiaohongshu)
- `publish/` — Publishers per platform, uses social-auto-upload for actual upload
- `publish/cookie_bridge.py` — Syncs storage_state to social-auto-upload conf.py

**Other Services:**
- `whisper_service.py` — Local Whisper STT wrapper
- `youtube.py` / `ytdlp_wrapper.py` — YouTube download
- `title_generator.py` — AI title/tag generation
- `channel_scanner.py` — APScheduler periodic channel scan
- `discovery_scanner.py` — Content discovery loop
- `config_seeder.py` — Default app_config initialization (33 keys)

### 3. Data Layer (`backend/app/models/`)
12 SQLAlchemy ORM models:

| Model | Table | Key Fields |
|-------|-------|------------|
| Video | `videos` | url, status, title, platform |
| Task | `tasks` | video_id, type, status, progress |
| Channel | `channels` | url, name, scan_interval |
| PublishRecord | `publish_records` | video_id, platform, status |
| Subtitle | `subtitles` | video_id, lang, segments (JSON) |
| Config | `app_config` | key, value, group |
| ScanLog | `scan_logs` | channel_id, results (JSON) |
| DiscoveryResult | `discovery_results` | url, score, reason |
| DiscoveryScanLog | `discovery_scan_logs` | run_id, count, new_items |

**State Machine** (video.status):
```
pending → downloading → transcribed → translated → synthesized → composed → published
    ↓          ↓             ↓             ↓             ↓             ↓
   failed    failed        failed        failed        failed        failed
```

### 4. Frontend Layer (`frontend/src/`)
Vue 3 SPA with Composition API + `<script setup lang="ts">`:

- **Router** (`router/index.ts`): 5 routes (Dashboard, Discover, Tasks, SubtitleEditor, Settings) + 4 legacy redirects
- **Stores** (`stores/`): 6 Pinia stores (configStore, discoveryStore, taskStore, videoStore, wsStore)
- **Views** (`views/`): 7 page components
- **Components** (`components/`): 4 shared components (AiTitleSelector, DubCreateDialog, PlatformLoginDrawer, VideoCard)
- **API** (`api/index.ts`): Single axios client with all endpoint methods

### 5. CLI Layer (`backend/app/cli.py`)
Command-line interface with 3 commands:
- `dub <url>` — Download + process a YouTube video
- `status` — Check task status
- `resume` — Resume a failed/interrupted task

## Data Flow (End-to-End)

```
YouTube URL
    ↓ yt-dlp download
Video file + audio
    ↓ Whisper STT
Transcript (JSON segments with timestamps)
    ↓ SiliconFlow translation (sliding window)
Translated segments (Chinese)
    ↓ CosyVoice2 TTS
Audio segments (per subtitle)
    ↓ ffmpeg speed alignment + compose
Dubbed video with mixed audio
    ↓ AI title generation
Video with titles + tags
    ↓ social-auto-upload publish
Published to 5 platforms
```

## Key Design Decisions

- **SQLite**: Simplicity for single-user/small-team deployment; WAL mode for concurrent reads
- **Polling scheduler**: Instead of message queue (RabbitMQ/Redis) — keeps dependencies minimal
- **Provider pattern**: `BaseTTSProvider` enables swapping TTS backends without pipeline changes
- **Vendored social-auto-upload**: Avoids pip dependency on external repo; sync strategy via cookie_bridge
- **ProactorEventLoop**: Windows workaround in `start_server.py` for Playwright subprocess compatibility
