# Directory Structure

**Generated:** 2026-06-30
**Focus:** arch

## Root Layout

```
VidDub/
├── backend/              # ~129 source files (Python)
├── frontend/             # ~28 source files (Vue/TS)
├── docs/                 # 8 documentation files
├── social-auto-upload/   # Vendored publishing library
├── scripts/              # Standalone utilities
├── .github/              # Issue/PR templates
├── .planning/            # GSD planning artifacts (gitignored)
├── docker-compose.yml    # Docker orchestration
├── Dockerfile            # Multi-stage build
├── README.md             # Chinese README (default)
├── README_EN.md          # English README
├── AGENTS.md             # Project knowledge base
├── CONTRIBUTING.md       # Contribution guide
├── CODE_OF_CONDUCT.md    # Code of conduct
├── SECURITY.md           # Security policy
├── CHANGELOG.md          # Version changelog
├── LICENSE               # MIT License
├── setup.ps1 / setup.sh  # Setup scripts (NOT YET COMMITTED)
├── start.bat / start.sh  # Startup scripts
└── .gitignore
```

## Backend Structure (`backend/`)

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app factory + lifespan
│   ├── cli.py               # CLI entry (dub/status/resume)
│   ├── api/                 # 17 route modules
│   │   ├── __init__.py
│   │   ├── router.py        # Central route registration
│   │   ├── videos.py, tasks.py, config.py, stats.py
│   │   ├── discovery.py, subtitles.py, transcription.py
│   │   ├── tts.py, voice_clone.py, dub.py
│   │   ├── platform.py, publish.py, title.py
│   │   ├── channels.py, export.py
│   ├── core/                # Infrastructure
│   │   ├── __init__.py
│   │   ├── config.py        # pydantic-settings (env + app_config)
│   │   ├── database.py      # AsyncSession factory
│   │   ├── websocket.py     # WebSocket manager
│   │   └── storage.py       # File storage helpers
│   ├── models/              # 12 SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── base.py          # DeclarativeBase
│   │   ├── enums.py         # VideoStatus, TaskType, etc.
│   │   ├── video.py, task.py, channel.py, subtitle.py
│   │   ├── config.py, publish_record.py, scan_log.py
│   │   ├── discovery.py, discovery_scan_log.py
│   ├── schemas/             # EMPTY — schemas are inline in api/
│   └── services/            # Business logic
│       ├── __init__.py
│       ├── scheduler.py     # ★ Core orchestrator (TaskScheduler)
│       ├── whisper_service.py
│       ├── youtube.py / ytdlp_wrapper.py
│       ├── title_generator.py
│       ├── channel_scanner.py / discovery_scanner.py
│       ├── config_seeder.py
│       ├── dubbing/         # ffmpeg pipeline
│       │   ├── pipeline.py, ffmpeg.py, alignment.py
│       │   ├── stitcher.py, composer.py
│       │   ├── subtitle_burn.py, voice_cloner.py
│       │   ├── audio_separation.py, paths.py
│       ├── siliconflow/     # API client + translation
│       ├── tts_new/         # Provider-pattern TTS (new)
│       │   ├── base.py, service.py, siliconflow_provider.py
│       ├── platform/        # Login managers (5 platforms)
│       │   ├── base.py, manager.py
│       │   ├── bilibili.py, douyin.py, kuaishou.py
│       │   ├── tencent.py, xiaohongshu.py
│       ├── platforms/       # REDUNDANT — only registry.py
│       ├── publish/         # Publishers (5 platforms)
│       │   ├── base.py, manager.py
│       │   ├── sau_bilibili.py, cookie_bridge.py
│       │   ├── douyin.py, kuaishou.py
│       │   ├── tencent.py, xiaohongshu.py
│       │   └── title_translate.py
│       ├── transcriber/     # STT provider pattern
│       │   ├── base.py, service.py
│       │   ├── whisper_provider.py, siliconflow_provider.py
│       └── voice_cloner/    # Voice cloning
│           ├── service.py, siliconflow_provider.py
├── alembic/                 # Database migrations
│   ├── env.py, script.py.mako
│   └── versions/            # 9 migration scripts
├── tests/                   # Test suite
│   ├── __init__.py, conftest.py
│   ├── unit/                # 15+ unit test files
│   ├── integration/         # 4 integration test files
│   └── fixtures/            # Test audio files, expected outputs
├── data/                    # SQLite DB (gitignored)
├── downloads/               # Video output (gitignored)
├── venv/                    # Virtual environment (gitignored)
├── requirements.txt
├── pytest.ini
├── .env / .env.example
└── start_server.py          # Windows ProactorEventLoop launcher
```

## Frontend Structure (`frontend/`)

```
frontend/
├── src/
│   ├── main.ts              # App bootstrap
│   ├── App.vue              # Root component
│   ├── constants.ts         # Shared constants
│   ├── env.d.ts             # Type declarations
│   ├── api/
│   │   └── index.ts         # Axios client + all endpoints
│   ├── router/
│   │   └── index.ts         # Routes config
│   ├── stores/
│   │   ├── index.ts         # Pinia setup
│   │   ├── configStore.ts
│   │   ├── videoStore.ts
│   │   ├── taskStore.ts
│   │   ├── discoveryStore.ts
│   │   └── wsStore.ts
│   ├── views/
│   │   ├── DashboardView.vue
│   │   ├── TasksView.vue
│   │   ├── DiscoverView.vue
│   │   ├── ChannelsView.vue
│   │   ├── SubtitleEditorView.vue
│   │   ├── PublishHistoryView.vue
│   │   └── SettingsView.vue
│   ├── components/
│   │   ├── VideoCard.vue
│   │   ├── DubCreateDialog.vue
│   │   ├── AiTitleSelector.vue
│   │   └── PlatformLoginDrawer.vue
│   ├── layouts/
│   │   └── MainLayout.vue
│   ├── styles/
│   │   └── theme.css
│   └── utils/
│       └── websocket.ts
├── package.json
├── vite.config.ts
├── tsconfig.json / tsconfig.node.json
└── index.html
```

## Documentation (`docs/`)

```
docs/
├── ARCHITECTURE.md       # System architecture (Chinese)
├── API.md                # API endpoint reference
├── CONFIGURATION.md      # All config keys documented
├── DEPLOYMENT.md         # Production deployment guide
├── DESIGN.md             # UX design documentation
├── REFACTOR_PLAN.md      # Refactoring plan
├── SOCIAL_AUTO_UPLOAD.md # Publishing library setup
└── TROUBLESHOOTING.md    # Common issues
```

## Key Naming Conventions

- **Python files**: snake_case (e.g., `whisper_service.py`, `title_generator.py`)
- **TypeScript files**: camelCase (e.g., `configStore.ts`, `wsStore.ts`)
- **Vue components**: PascalCase (e.g., `VideoCard.vue`, `AiTitleSelector.vue`)
- **API route modules**: snake_case (e.g., `voice_clone.py`, `publish.py`)
- **Database tables**: snake_case (e.g., `publish_records`, `scan_logs`)
- **Directory names**: lowercase (e.g., `tts_new/`, `social-auto-upload/`)
