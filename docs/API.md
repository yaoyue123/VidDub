# API 速览

> You2Bili 后端 FastAPI 提供的所有 REST 端点 + WebSocket 事件清单。
> **最权威文档**：启动后端后访问 **http://localhost:8000/docs**（Swagger UI）或 **http://localhost:8000/redoc**（ReDoc）。

---

## 互动文档

FastAPI 自动生成 OpenAPI 3 文档，运行时即可交互测试：

| 文档类型 | URL | 说明 |
|----------|-----|------|
| Swagger UI | http://localhost:8000/docs | 在线调试，可点击 "Try it out" 直接发请求 |
| ReDoc | http://localhost:8000/redoc | 只读、排版优雅，适合阅读 |
| OpenAPI JSON | http://localhost:8000/openapi.json | 原始 schema，可导入 Postman / Apifox |

---

## REST 端点分组

### 1. Discovery / 发现（`/api/discovery`）

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/discovery/search` | YouTube 关键字搜索 |
| GET | `/api/discovery/channels` | 查询 YouTube 频道信息 |
| GET | `/api/discovery/channel/{id}/videos` | 列出频道视频 |

### 2. Videos / 视频（`/api/videos`）

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/videos` | 视频列表（支持分页/筛选） |
| POST | `/api/videos` | 手动添加视频（旧入口，Phase 4 后建议用 `/api/dub`） |
| GET | `/api/videos/{id}` | 视频详情 |
| DELETE | `/api/videos/{id}` | 删除视频 |

### 3. Dub / 配音（`/api/dub`，Phase 4）

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/dub` | **创建端到端配音任务**：body `{youtube_url}` → 启动 6 步 chain |
| GET | `/api/dub/{id}` | 查询任务进度：返回 `status / progress_pct / current_step / error_msg / final_url / srt_url` |
| GET | `/api/dub/{id}/download` | 下载 `final.mp4`（流式） |
| GET | `/api/dub/{id}/subtitle` | 下载 SRT 字幕（中文） |
| GET | `/api/dub/{id}/preview/{kind}` | 预览音频（`kind=dubbing\|final\|original`） |
| POST | `/api/dub/{id}/resume` | 断点续跑（从 `failed` 状态恢复） |

### 4. Subtitles / 字幕（`/api/subtitles`）

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/subtitles/{video_id}` | 获取字幕列表（双语） |
| PUT | `/api/subtitles/{id}` | 编辑单条字幕（自动保存） |
| POST | `/api/subtitles/{video_id}/retranslate?segment_index=N` | 单段重新翻译（调 SiliconFlow） |

### 5. Tasks / 任务（`/api/tasks`）

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/tasks` | 任务列表（支持 `status / type / source / date_from / date_to / include_deleted` 过滤） |
| GET | `/api/tasks/{id}` | 任务详情 |
| POST | `/api/tasks/batch` | 批量操作：body `{ids, action}` — action ∈ `pause \| resume \| retry \| delete` |

### 6. Platform / 平台登录（`/api/platform`，Phase 6）

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/platform/{platform}/login/start` | 启动扫码：platform ∈ `bilibili \| ixigua`，返回 `qr_image_base64 + expires_at` |
| GET | `/api/platform/{platform}/login/poll` | HTTP 短轮询（备用，正常靠 WS 推送） |
| GET | `/api/platform/{platform}/login/status` | 查询本地 `storage_state`（不联网） |
| GET | `/api/platform/{platform}/check` | 主动调平台 API 检测登录态过期 |
| POST | `/api/platform/{platform}/logout` | 清除 `storage_state` |
| GET | `/api/platform/state` | 所有平台登录态总览（Dashboard 用） |

### 7. Publish / 发布（`/api/publish`，Phase 7）

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/publish/trigger` | 手动触发发布：body `{video_id, platform}` |
| GET | `/api/publish/auto` | 查询自动发布开关状态 |
| PUT | `/api/publish/auto` | 修改自动发布开关 |
| GET | `/api/publish/records` | 发布历史（支持 platform 过滤、分页） |
| GET | `/api/publish/records/{id}` | 单条发布详情 |
| POST | `/api/publish/records/{id}/retry` | 重试失败的发布 |

### 8. Title / AI 标题（`/api/title`，Phase 8）

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/title/{video_id}/generate` | 触发 AI 标题生成（SiliconFlow JSON mode） |
| GET | `/api/title/{video_id}` | 读取候选 + 用户已选 |
| PUT | `/api/title/{video_id}` | 保存用户选择：body `{title_chosen, tags_chosen}` |

### 9. Channels / 频道（`/api/channels`，Phase 9）

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/channels` | 频道列表 |
| POST | `/api/channels` | 新增频道：body `{name, url, scan_interval_hours, filter_min_views, ...}` |
| GET | `/api/channels/{id}` | 频道详情 |
| PUT | `/api/channels/{id}` | 修改频道 |
| DELETE | `/api/channels/{id}` | 删除频道 |
| POST | `/api/channels/{id}/scan-now` | 立即扫描 |
| GET | `/api/channels/{id}/scan-logs?limit=50` | 扫描日志 |

### 10. Stats / 统计（`/api/stats`）

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/stats/dashboard` | Dashboard 数据：`{today_count, success_rate, avg_duration_sec, recent_tasks[], failed_tasks[]}` |

### 11. Config / 配置（`/api/config`）

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/config` | 列出所有 `app_config` 项 |
| PUT | `/api/config/{key}` | 修改单项 |
| POST | `/api/config/test-siliconflow` | 测试 SiliconFlow 连通性（用 tiny TTS payload） |

### 12. Export / 导出（`/api/export`，Phase 9）

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/export/tasks?format=csv\|json&status=&date_from=&date_to=` | 流式导出任务（CSV / JSON） |

### 13. 其它历史接口（Phase 1-3，向后兼容保留）

| 路径前缀 | 说明 |
|----------|------|
| `/api/transcription` | 旧 Whisper 直转接口（已被 `/api/dub` 取代） |
| `/api/tts` | 单独 TTS 接口（语音克隆预览用） |
| `/api/voice-clone` | 上传参考音频 → 注册自定义音色 |
| `/api/upload` | 旧 Bilibili 上传 SDK 入口（已被 `/api/publish` 取代） |
| `/api/dubbing` | 旧配音组装接口（已被 `/api/dub` 取代） |

---

## WebSocket 事件

**连接**：`ws://localhost:8000/ws`

所有事件结构：`{type: "<event_name>", data: {...}}`

### Task 相关

| 事件 | 触发时机 | data 关键字段 |
|------|----------|---------------|
| `task_created` | 新任务入队 | `{task_id, video_id, task_type}` |
| `task_start` | scheduler 开始处理 | `{task_id, video_id, step}` |
| `task_progress` | 步骤进度更新 | `{task_id, video_id, progress, current_step, status}` |
| `task_complete` | 整条 chain 完成 | `{video_id, final_url, srt_url}` |
| `task_error` | 任何步骤失败 | `{video_id, task_id, error, step, recoverable}` |

### Platform Login 相关（Phase 6）

| 事件 | 触发时机 | data 关键字段 |
|------|----------|---------------|
| `platform_qr_update` | 二维码刷新（每 30s） | `{platform, qr_image_base64, expires_at}` |
| `platform_login_status` | 扫码状态变化 | `{platform, status: waiting\|scanned\|success\|failed\|timeout, user_info?}` |
| `platform_login_expired` | 30 分钟检测到过期 | `{platform}` |

### Publish 相关（Phase 7）

| 事件 | 触发时机 | data 关键字段 |
|------|----------|---------------|
| `publish_start` | 发布开始 | `{video_id, platform}` |
| `publish_progress` | 发布进度 | `{video_id, platform, stage: uploading\|processing\|filling\|submitting, pct}` |
| `publish_complete` | 发布成功 | `{video_id, platform, platform_url}` |
| `publish_error` | 发布失败 | `{video_id, platform, error, needs_relogin}` |

### Title 相关（Phase 8）

| 事件 | 触发时机 | data 关键字段 |
|------|----------|---------------|
| `title_start` | AI 标题生成开始 | `{video_id}` |
| `title_complete` | 候选已写入 DB | `{video_id, candidate_count}` |
| `title_error` | 生成失败（容错，不阻塞发布） | `{video_id, error}` |

---

## 鉴权

**无鉴权**。本工具设计为本地个人使用，FastAPI 监听 `127.0.0.1`。生产部署暴露公网时必须放在反向代理 + 加 IP 白名单 / Basic Auth 后面，参见 [DEPLOYMENT.md](DEPLOYMENT.md)。

---

## 调用示例

### 创建配音任务

```bash
curl -X POST http://localhost:8000/api/dub \
  -H "Content-Type: application/json" \
  -d '{"youtube_url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

### 查询进度

```bash
curl http://localhost:8000/api/dub/1
```

### 触发 AI 标题生成

```bash
curl -X POST http://localhost:8000/api/title/1/generate
```

### 批量重试失败任务

```bash
curl -X POST http://localhost:8000/api/tasks/batch \
  -H "Content-Type: application/json" \
  -d '{"ids":[1,2,3],"action":"retry"}'
```

### 导出 CSV

```bash
curl "http://localhost:8000/api/export/tasks?format=csv&status=completed" \
  -o completed_tasks.csv
```

---

*本文档对应 Phase 10 (v2.0.10) · 完整 OpenAPI schema 以运行时 `/docs` 为准*
