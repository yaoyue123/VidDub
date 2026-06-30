# External Integrations

**Generated:** 2026-06-30
**Focus:** tech

## SiliconFlow API

| Aspect | Detail |
|--------|--------|
| **Base URL** | `https://api.siliconflow.cn` |
| **Auth** | API key via `SILICONFLOW_API_KEY` env var |
| **Services Used** | Chat completion (translation), TTS (CosyVoice2), JSON mode (title generation) |
| **Models** | Translation: Qwen2.5-7B/14B/72B, DeepSeek-V2.5, DeepSeek-V4-Flash. TTS: CosyVoice2-0.5B |
| **Source** | `backend/app/services/siliconflow/client.py` — unified async HTTP client with retry |

**Translation Integration:** `backend/app/services/siliconflow/translate.py` — sliding window context for coherence, batch fallback to segment-by-segment on failure.

**TTS Integration:** Two paths:
- Legacy: `backend/app/services/siliconflow/tts.py` (old, being phased out)
- New: `backend/app/services/tts_new/siliconflow_provider.py` (provider pattern, 2026-06-25)

**Title Generation:** `backend/app/services/title_generator.py` — uses SiliconFlow JSON mode to generate 5 title candidates + 8 tags.

## YouTube

| Aspect | Detail |
|--------|--------|
| **Method** | yt-dlp (open source CLI, installed via pip) |
| **Purpose** | Video + audio download with metadata |
| **Wrapper** | `backend/app/services/ytdlp_wrapper.py` — rate limiter + circuit breaker |
| **Legacy** | `backend/app/services/youtube.py` — older wrapper |
| **Features** | Format selection, subtitles extraction, thumbnail download |

## External File Processing

| Service | Integration | Location |
|---------|-------------|----------|
| ffmpeg | System PATH (subprocess) | `backend/app/services/dubbing/ffmpeg.py` |

## External Dependencies (No API)

- **Local Whisper**: Model downloaded on first run (tiny ~1.5GB, base/small/medium options in config)
- **Playwright**: Chromium browser downloaded by `playwright install chromium` for platform login automation
- **Edge TTS**: Microsoft Edge TTS as fallback TTS provider

## Database

| Aspect | Detail |
|--------|--------|
| **Engine** | SQLite 3 |
| **Driver** | aiosqlite (async) |
| **File** | `backend/data/viddub.db` |
| **Features** | WAL mode, FTS5 for subtitle search |
| **Config storage** | Hybrid: `.env` for secrets, `app_config` SQLite table for runtime settings |

## No Monitoring / No APM

The project has no integrated monitoring, logging aggregation, or APM tooling. Logs are written to stdout/stderr via Python logging module. No Sentry, Datadog, or similar.
