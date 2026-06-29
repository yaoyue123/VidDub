# 配置项完整说明

> VidDub 所有可配置项的清单。`.env` 用于敏感数据（API Key），`app_config` 表用于运行时可调参数。

---

## 一、`.env` 环境变量（`backend/.env`）

`.env` 由 `pydantic-settings` 在启动时加载，所有字段在 `app/core/config.py` 的 `Settings` 类定义。

| 变量名 | 必填 | 默认 | 说明 |
|--------|------|------|------|
| `SILICONFLOW_API_KEY` | **是** | — | SiliconFlow API Key，配音/翻译/标题全部依赖。申请：https://cloud.siliconflow.cn/account/ak |
| `SILICONFLOW_BASE_URL` | 否 | `https://api.siliconflow.cn/v1` | API base URL，第三方代理可改 |
| `SILICONFLOW_TTS_MODEL` | 否 | `FunAudioLLM/CosyVoice2-0.5B` | TTS 模型名（覆盖 `app_config.tts_model`） |
| `SILICONFLOW_TRANSLATE_MODEL` | 否 | `Qwen/Qwen2.5-7B-Instruct` | 翻译模型名（覆盖 `app_config.translation_model`） |
| `WHISPER_MODEL` | 否 | `tiny` | 本地 Whisper 模型：`tiny\|base\|small\|medium\|large`（覆盖 `app_config.whisper_model`） |
| `WHISPER_LANGUAGE` | 否 | `en` | Whisper 源语言代码：`en\|zh\|ja\|...` |
| `DOWNLOADS_DIR` | 否 | `./downloads` | 视频成品输出目录 |
| `DATABASE_URL` | 否 | `sqlite+aiosqlite:///./data/viddub.db` | 数据库连接串（建议保持 SQLite） |
| `HTTP_PROXY` | 否 | — | 出站 HTTP 代理（如有） |
| `HTTPS_PROXY` | 否 | — | 出站 HTTPS 代理 |

### `.env` 模板（`.env.example`）

```dotenv
# SiliconFlow API Credentials
SILICONFLOW_API_KEY=

# Optional overrides
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_TTS_MODEL=FunAudioLLM/CosyVoice2-0.5B
SILICONFLOW_TRANSLATE_MODEL=Qwen/Qwen2.5-7B-Instruct

WHISPER_MODEL=tiny
WHISPER_LANGUAGE=en

DOWNLOADS_DIR=./downloads
DATABASE_URL=sqlite+aiosqlite:///./data/viddub.db

# Network (optional, for proxy)
# HTTP_PROXY=http://127.0.0.1:7890
# HTTPS_PROXY=http://127.0.0.1:7890
```

---

## 二、`app_config` 表配置项（运行时通过 `/api/config` 或 Web UI 修改）

所有项以字符串存储，由业务代码按需类型转换。首次启动 `config_seeder.py` 自动 seed 默认值。

### 2.1 SiliconFlow / 翻译 / TTS

| Key | 默认 | 类型 | 说明 |
|-----|------|------|------|
| `translation_api_key` | `""` | string | SiliconFlow API Key（与 `.env` 重复，二选一即可；优先用 `.env`） |
| `translation_api_base_url` | `https://api.siliconflow.cn/v1` | URL | 翻译 API base URL |
| `translation_model` | `Qwen/Qwen2.5-7B-Instruct` | string | 翻译模型名 |
| `translation_context_window` | `"2"` | int (作为 str) | 翻译滑窗上下文段数（建议 2-4） |
| `tts_model` | `FunAudioLLM/CosyVoice2-0.5B` | string | TTS 模型名 |
| `tts_voice` | `FunAudioLLM/CosyVoice2-0.5B:alex` | string | 完整音色 ID（含模型前缀） |
| `tts_voice_simple` | `"alex"` | string | 简短音色名（自动拼模型前缀，如 `alex`） |
| `tts_speed` | `"1.0"` | float | 语速 0.25 - 4.0 |
| `tts_gain` | `"0"` | int (dB) | 音量增益 -10 ~ +10 |
| `tts_format` | `"mp3"` | enum | 输出格式：`mp3\|wav\|opus\|pcm` |
| `tts_sample_rate` | `"32000"` | int (Hz) | 采样率 |
| `dubbing_voice` | `zh-CN-XiaoxiaoNeural` | string | （旧 edge-tts 字段，v2.0 用 `tts_voice_simple`） |
| `dubbing_rate` | `+0%` | string | （旧 edge-tts 字段） |

### 2.2 Whisper / STT

| Key | 默认 | 类型 | 说明 |
|-----|------|------|------|
| `whisper_model` | `"tiny"` | enum | 本地 Whisper 模型：`tiny\|base\|small\|medium` |
| `whisper_language` | `"en"` | ISO code | Whisper 源语言（auto = 自动检测，但英文视频建议固定 `en`） |
| `stt_model` | `"whisper-local"` | string | STT 后端标识（保留兼容，实际固定本地 Whisper） |
| `transcription_backend` | `"whisper"` | enum | `whisper\|siliconflow`（Phase 4 后固定 `whisper`） |
| `transcription_model` | `FunAudioLLM/SenseVoiceSmall` | string | SiliconFlow STT 模型（D-17 pivot 后未使用） |
| `target_language` | `"zh"` | ISO code | 翻译目标语言 |

### 2.3 音频对齐 / 时间控制（Phase 4）

| Key | 默认 | 类型 | 说明 |
|-----|------|------|------|
| `atempo_min` | `"0.7"` | float | atempo 调速下限 — 中文 TTS 比原文长且 `duration/original < 0.7` 时改为 pad 静音（不强行加速） |
| `atempo_max` | `"1.5"` | float | atempo 调速上限 — 中文 TTS 比原文短且 `duration/original > 1.5` 时改为 trim 截断（不强行降速） |

> **范围说明**：建议保持 0.7-1.5x。低于 0.5x 听感明显异常；高于 2.0x ffmpeg atempo 需链式两段。

### 2.4 视频下载 / 通用

| Key | 默认 | 类型 | 说明 |
|-----|------|------|------|
| `download_dir` | `./downloads` | path | 视频成品输出目录（每个 video 一个子目录） |
| `max_resolution` | `"1080"` | enum | 最大下载分辨率：`720\|1080\|2160` |
| `max_concurrent_downloads` | `"3"` | int | 最大并发下载数 |
| `max_results_per_search` | `"20"` | int | 每次搜索最大返回数 |
| `yt_dlp_cookies` | `""` | path | yt-dlp Cookie 文件路径（可选，YouTube 风控严格时使用） |

### 2.5 自动发布（Phase 7）

| Key | 默认 | 类型 | 说明 |
|-----|------|------|------|
| `auto_publish_enabled` | `"true"` | bool (str) | 配音完成后是否自动发布。`true\|false` |
| `default_upload_platform` | `"xigua"` | enum | 默认上传平台（旧字段）：`xigua\|bilibili` |
| `bilibili_default_category` | `"122"` | int | 哔哩哔哩默认分区 tid（`122=野生技术协会`，`95=数码`，`207=科技>科普`） |
| `ixigua_default_copyright` | `"repost"` | enum | 西瓜视频版权类型：`original=原创\|repost=转载` |
| `publish_default_tags` | `搬运,英语学习,翻译` | CSV string | 发布默认标签（最多 10 个） |
| `publish_retry_max` | `"3"` | int | 发布失败最大重试次数 |
| `publish_upload_timeout_sec` | `"600"` | int (sec) | 视频上传 + 平台处理最长等待秒数（默认 10 分钟） |

### 2.6 AI 标题与标签（Phase 8）

| Key | 默认 | 类型 | 说明 |
|-----|------|------|------|
| `title_generator_enabled` | `"true"` | bool (str) | 配音完成后是否自动生成 AI 标题 |
| `title_generator_candidate_count` | `"5"` | int | 候选标题数量（默认 5） |
| `title_generator_tag_count` | `"8"` | int | 候选标签数量（默认 8，Bilibili 上限 10，留 2 空位给默认标签） |

### 2.7 定时扫描 / 频道管理（Phase 9）

| Key | 默认 | 类型 | 说明 |
|-----|------|------|------|
| `scan_max_concurrent` | `"3"` | int | 频道扫描最大并发数 |
| `scan_default_interval_hours` | `"6"` | enum | 默认扫描间隔小时：`1\|3\|6\|12\|24` |

### 2.8 平台登录 Cookie（旧字段，已被 `storage_state.json` 替代）

| Key | 默认 | 说明 |
|-----|------|------|
| `bili_sessdata` | `""` | （旧）Bilibili SESSDATA cookie |
| `bili_bili_jct` | `""` | （旧）Bilibili bili_jct CSRF cookie |
| `bili_dedeuserid` | `""` | （旧）Bilibili DedeUserID cookie |
| `xigua_cookies_json` | `""` | （旧）西瓜 cookie JSON |
| `upload_default_tags` | `技术,YouTube,搬运` | （旧）默认上传标签 |
| `upload_default_tid` | `"122"` | （旧）Bilibili 默认 tid |

> **提示**：Phase 6+ 使用 Playwright `storage_state.json`（存在 `backend/data/login/`），不再需要手动维护这些 cookie 字段。

### 2.9 已废弃字段（保留向后兼容）

| Key | 默认 | 状态 |
|-----|------|------|
| `ollama_base_url` | `http://localhost:11434` | v2.0 弃用（改用 SiliconFlow） |
| `ollama_model` | `qwen2.5:7b` | v2.0 弃用 |

---

## 三、配置修改方式

### 方式 1：Web UI（推荐）

启动后访问 http://localhost:5173/settings，5 个 tab：
- **SiliconFlow**：API Key + base URL + 模型选择 + 连通性测试
- **STT (Whisper)**：模型大小 + 源语言
- **TTS**：音色 + 语速 + 音量 + 格式
- **Translate**：翻译模型 + 滑窗上下文
- **Advanced**：下载/发布/扫描等高级参数

### 方式 2：REST API

```bash
# 读所有配置
curl http://localhost:8000/api/config

# 改单项
curl -X PUT http://localhost:8000/api/config/whisper_model \
  -H "Content-Type: application/json" \
  -d '{"value":"base"}'

# 测试 SiliconFlow 连通性
curl -X POST http://localhost:8000/api/config/test-siliconflow
```

### 方式 3：直接改 DB（不推荐，调试用）

```bash
sqlite3 backend/data/viddub.db
> SELECT key, value FROM app_config;
> UPDATE app_config SET value='base' WHERE key='whisper_model';
```

修改后需重启 uvicorn 让某些缓存失效（Pydantic Settings 类只读 `.env`，DB 配置每次请求实时读）。

---

## 四、典型配置场景

### 场景 1：低配电脑（CPU 跑得慢）

```dotenv
WHISPER_MODEL=tiny
```
- 把 `atempo_min` 调到 `0.5`（容忍更慢语速）
- `max_concurrent_downloads=1`

### 场景 2：高质量需求（GPU 充足）

```dotenv
WHISPER_MODEL=small      # 或 medium
```
- Web UI 改 `tts_speed=0.95`（更自然）
- `atempo_min=0.8` `atempo_max=1.3`（容忍范围窄，更自然）

### 场景 3：批量自动化（24/7 运行）

- `auto_publish_enabled=true`
- 频道扫描 `scan_interval_hours=6`
- `max_concurrent_downloads=2`（避免触发 YouTube 风控）
- `publish_retry_max=5`

### 场景 4：仅做翻译，不发布

- `auto_publish_enabled=false`
- 完成后通过 `GET /api/dub/{id}/download` 手动取走 mp4 + SRT

---

*本文档对应 Phase 10 (v2.0.10) · 完整默认值定义见 `backend/app/services/config_seeder.py` 的 `DEFAULT_CONFIGS` dict*
