# 架构文档

> You2Bili v2.0 — YouTube 视频中文配音 + 自动发布系统的整体架构、数据流、模块依赖、状态机。

---

## 1. 系统架构总览

```mermaid
flowchart LR
    User([用户])
    Browser[浏览器]

    subgraph Frontend["Frontend (Vue 3 + Vite)"]
        UI[Web UI<br/>Dashboard / Tasks / Settings<br/>Platform / Publish / Channels / Subtitle]
        Pinia[(Pinia Store)]
        WSClient[WebSocket Client]
        Axios[axios HTTP]
    end

    subgraph Backend["Backend (FastAPI + uvicorn)"]
        Router[FastAPI Router<br/>18 个 API 模块]
        WS[WebSocket Manager]

        subgraph Services["Services 业务层"]
            Sched[TaskScheduler<br/>配音 chain 编排]
            Scanner[ChannelScanner<br/>APScheduler 定时]
            YT[YouTube Service<br/>yt-dlp]
            Whisper[Whisper Service<br/>本地 STT]
            SF[SiliconFlow Client<br/>httpx + tenacity]
            SFTranslate[Translate Service<br/>Qwen2.5-7B]
            SFTTS[TTS Service<br/>CosyVoice2-0.5B]
            FF[ffmpeg 编排层<br/>extract/atempo/stitch/compose]
            AI[Title Generator<br/>JSON mode]
            PlatMgr[Platform Login<br/>Manager]
            PubMgr[Publish Manager]
            Browser2[Playwright<br/>Chromium]
        end

        subgraph DB["数据库 (SQLite)"]
            Videos[videos]
            Tasks[tasks]
            Configs[app_config]
            Subtitles[subtitles]
            Channels[channels]
            ScanLogs[scan_logs]
            PubRecords[publish_records]
        end
    end

    subgraph External["外部服务"]
        YT2[YouTube<br/>视频源]
        SFApi[SiliconFlow API<br/>translate/tts/title]
        Bili[哔哩哔哩]
        Xigua[西瓜视频]
        WH[~/.cache/whisper/<br/>模型缓存]
    end

    User -->|访问 :5173| Browser --> UI
    UI <--> Axios
    Axios -->|HTTP :8000| Router
    UI <-->|WS :8000/ws| WSClient <--> WS

    Router --> Sched
    Router --> Scanner
    Router --> YT & Whisper & SF & AI & PlatMgr & PubMgr & Configs

    Sched --> YT --> YT2
    Sched --> Whisper --> WH
    Sched --> SF
    SF --> SFTranslate & SFTTS
    SF --> SFApi
    Sched --> FF
    FF -->|subprocess| FFbin[ffmpeg binary]
    Sched --> AI --> SF
    Sched --> PubMgr --> Browser2
    PubMgr --> Bili & Xigua
    PlatMgr --> Browser2 --> Bili & Xigua
    Scanner --> YT

    Sched & Router & Scanner -.写.-> Videos & Tasks & Subtitles & Channels & ScanLogs & PubRecords
```

---

## 2. 核心数据流 — 从 URL 到发布的完整链路

```mermaid
sequenceDiagram
    participant U as 用户
    participant W as Web UI
    participant API as FastAPI
    participant SCH as TaskScheduler
    participant YT as yt-dlp
    participant WH as Whisper (本地)
    participant SF as SiliconFlow
    participant FF as ffmpeg
    participant PL as Playwright
    participant DB as SQLite

    U->>W: 粘贴 YouTube URL
    W->>API: POST /api/dub {url}
    API->>DB: INSERT video(pending) + task(download)
    API-->>W: 202 {video_id}
    API->>SCH: 触发 chain

    Note over SCH: === 步骤 1: 下载 ===
    SCH->>YT: 下载视频
    YT-->>SCH: mp4 文件
    SCH->>DB: video.status=downloaded

    Note over SCH: === 步骤 2: 提取音频 + STT ===
    SCH->>FF: 提取 16kHz 单声道 wav
    SCH->>WH: transcribe(wav)
    WH-->>SCH: segments[{start,end,text}]
    SCH->>DB: 写 transcript.json + subtitles 行
    SCH->>DB: video.status=transcribed

    Note over SCH: === 步骤 3: 翻译 ===
    SCH->>SF: 批量翻译 [en→zh]
    SF-->>SCH: 翻译结果
    Note over SCH: 失败则回退到逐段
    SCH->>DB: 写 translated.json
    SCH->>DB: video.status=translated

    Note over SCH: === 步骤 4: TTS + 对齐 ===
    loop 每段 segment
        SCH->>SF: TTS(中文) → mp3
        SCH->>FF: atempo 对齐时长 (0.7x-1.5x)
    end
    SCH->>DB: video.status=synthesized

    Note over SCH: === 步骤 5: 拼接 + 合成视频 ===
    SCH->>FF: adelay+amix 拼接所有段 + apad 到视频时长
    SCH->>FF: 替换原音轨 → final.mp4
    SCH->>DB: 写 subtitle.srt (中文)
    SCH->>DB: video.status=composed

    Note over SCH: === 步骤 6: AI 标题 ===
    SCH->>SF: JSON mode 生成 5 标题 + 8 标签
    SF-->>SCH: candidates
    SCH->>DB: ai_title_candidates 等

    Note over SCH: === 步骤 7: 自动发布 (可选) ===
    SCH->>PL: Playwright 打开 creator.bilibili.com
    PL->>PL: 上传 final.mp4 + 填表
    PL-->>SCH: platform_url
    SCH->>DB: publish_record + video.status=published

    SCH-->>W: WS task_complete {final_url}
    U->>W: 查看进度 / 下载成品
```

---

## 3. 模块依赖图

```mermaid
graph TD
    subgraph API_Layer
        DubApi[dub.py]
        PlatApi[platform.py]
        PubApi[publish.py]
        TitleApi[title.py]
        ChanApi[channels.py]
        TaskApi[tasks.py]
        CfgApi[config.py]
        StatsApi[stats.py]
        SubApi[subtitles.py]
        ExpApi[export.py]
        DiscApi[discovery.py]
    end

    subgraph Service_Layer
        Scheduler[scheduler.py<br/>★ 核心]
        YouTube[youtube.py]
        WhisperSrv[whisper_service.py]
        DubPipe[dubbing/pipeline.py]
        SFFacade[siliconflow/<br/>client+translate+tts]
        TitleGen[title_generator.py]
        Scanner[channel_scanner.py]
        LoginMgr[platform/manager.py]
        PubMgr[publish/manager.py]
        PubTT[publish/title_translate.py]
    end

    subgraph Infra
        DB[(database.py)]
        Config[config.py + Settings]
        WS[websocket.py]
        ConfigSeeder[config_seeder.py]
    end

    DubApi --> Scheduler
    SubApi --> Scheduler
    PubApi --> PubMgr
    TitleApi --> TitleGen
    ChanApi --> Scanner
    TaskApi --> Scheduler
    CfgApi --> Config

    Scheduler --> YouTube
    Scheduler --> WhisperSrv
    Scheduler --> DubPipe
    Scheduler --> SFFacade
    Scheduler --> TitleGen
    Scheduler --> PubMgr
    Scheduler --> WS

    DubPipe --> SFFacade
    DubPipe --> FFbin2[ffmpeg binary]
    WhisperSrv --> WHCache[(whisper cache)]
    SFFacade --> SFHttp[SiliconFlow HTTP]
    PubMgr --> Playwright2[Playwright]
    PubMgr --> PubTT
    PubTT --> SFFacade
    LoginMgr --> Playwright2
    Scanner --> YouTube

    Scheduler -.写.-> DB
    Scanner -.写.-> DB
    ConfigSeeder -.seed.-> DB
```

---

## 4. Video.status 状态机（全流转图）

```mermaid
stateDiagram-v2
    [*] --> pending: POST /api/dub<br/>或 channel 自动扫描
    pending --> downloading: scheduler 开始处理
    downloading --> downloaded: yt-dlp 成功
    downloading --> failed: 网络错误/无字幕

    downloaded --> transcribing: chain 自动
    transcribing --> transcribed: Whisper 完成
    transcribing --> failed: Whisper 异常

    transcribed --> translating: chain 自动
    translating --> translated: SiliconFlow 翻译完成
    translating --> failed: API key 错误 / 限流不可恢复

    translated --> synthesizing: chain 自动
    synthesizing --> synthesized: TTS + atempo 对齐完成
    synthesizing --> failed: TTS 限流 / 段过长

    synthesized --> composing: chain 自动
    composing --> composed: ffmpeg 替换音轨 + 写 SRT
    composing --> failed: ffmpeg 命令失败 / 磁盘满

    composed --> published: 自动发布开启且成功
    composed --> [*]: 自动发布关闭<br/>(composed 即终态)

    published --> [*]

    failed --> pending: POST /api/dub/{id}/resume<br/>或 CLI resume
    failed --> [*]: 用户删除

    note right of pending
        初始状态
    end note

    note right of composed
        成品 mp4 + SRT 已生成
        可手动发布或自动发布
    end note
```

---

## 5. 关键设计决策

| ID | 决策 | 原因 |
|----|------|------|
| D-01 | API Key 直接放 `.env`，不入 DB | 简化部署；用户自用工具无多用户风险 |
| D-05 (pivot) | 放弃 BGM 保留，整轨替换 | Demucs 资源占用大、人声分离质量不稳定 |
| D-09 | atempo + pad/trim 时间对齐，调速 0.7-1.5x | 兼顾自然度和时长精度 |
| D-13/D-14 | 状态机去除 separating/mixed | 对应 D-05 决策 |
| D-17 (pivot) | STT 改用本地 Whisper | SiliconFlow SenseVoiceSmall 不返回 segment 时间戳 |
| Phase 4 Rule 1 | 翻译批量失败回退到逐段单独请求 | Qwen2.5-7B 常忽略 `[ID:N]` 格式 |
| Phase 6 | 哔哩哔哩走 HTTP QR API，西瓜走 Playwright | 哔哩官方 API 稳定；西瓜无公开 QR API |
| Phase 7 | Playwright headed 模式 | 模拟真实浏览器防风控；headless 易被识别 |
| Phase 8 | SiliconFlow Chat JSON mode | 一次调用拿标题+标签+摘要，比纯文本解析更稳 |
| Phase 9 | APScheduler 内存 jobstore | FastAPI 重启从 DB 重建；不依赖外部持久化 |

---

## 6. 并发与限流策略

| 资源 | 限制 | 实现 |
|------|------|------|
| TTS 并发 | 3 个 segment 并发 | `asyncio.Semaphore(3)` 在 `services/dubbing/pipeline.py` |
| 频道扫描 | 3 个频道并行 | `asyncio.Semaphore(scan_max_concurrent)` 在 `channel_scanner.py` |
| SiliconFlow HTTP 重试 | 最多 3 次 + 指数退避（2-30s） | `tenacity stop_after_attempt(3) + wait_exponential` |
| yt-dlp 进度推送 | 每 ~1s 节流 | yt-dlp progress_hook + asyncio.create_task 异步推 |
| WebSocket 广播 | 无节流（信任本地用户量） | `manager.broadcast(msg)` 单一 fan-out |

---

## 7. 文件 → 模块映射

| 模块 | 主文件 | 关键类/函数 |
|------|--------|-------------|
| 任务调度核心 | `app/services/scheduler.py` | `TaskScheduler`、`_handle_*` chain |
| YouTube 下载 | `app/services/youtube.py` | `YoutubeService.get_video_info / download_video / get_channel_videos` |
| Whisper STT | `app/services/whisper_service.py` | `WhisperService.transcribe` |
| SiliconFlow 客户端 | `app/services/siliconflow/client.py` | `SiliconFlowClient.chat / tts / translate_batch` |
| 翻译 | `app/services/siliconflow/translate.py` | `translate_segments`（批量+逐段回退） |
| TTS | `app/services/siliconflow/tts.py` | `synthesize_segment` |
| ffmpeg 编排 | `app/services/dubbing/{pipeline,ffmpeg,alignment,stitcher,composer,paths}.py` | 6 步流水线 |
| AI 标题 | `app/services/title_generator.py` | `generate_title_candidates` (JSON mode + 文本回退) |
| 平台登录 | `app/services/platform/{base,manager,bilibili,ixigua}.py` | `LoginManager` 单例 |
| 平台发布 | `app/services/publish/{base,manager,bilibili,ixigua,title_translate}.py` | `PublishManager` |
| 频道扫描 | `app/services/channel_scanner.py` | `ChannelScanner` + APScheduler |
| 配置 | `app/services/config_seeder.py` + `app/core/config.py` | `DEFAULT_CONFIGS` dict + Pydantic Settings |
| WebSocket | `app/core/websocket.py` | `ConnectionManager.broadcast` |

---

*本文档对应 Phase 10 (v2.0.10) · 最后更新：2026-06-22*
