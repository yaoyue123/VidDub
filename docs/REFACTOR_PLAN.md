# VidDub v4.0 — 架构重构计划

## 目标

消除重复配置、统一 API 接口、清理死代码、规范化架构，保证重构后项目正常运行且便于拓展。

---

## Phase 1: 配置系统统一化 (CRITICAL)

### 问题
- 4 套配置源并存：`.env` → `Settings` 类 → `os.getenv()` → DB `Config` 表
- API Key 存储在两个不同的 DB key 名下 (`translation_api_key` vs `siliconflow_api_key`)
- 新 adapter 读 `translation_api_key`，前端设 `siliconflow_api_key` → **桥接断裂**

### 方案: 单一配置源 + 统一命名

```
.env 文件 (唯一真相源)
    ↓
Settings 类 (pydantic-settings, 统一加载)
    ↓
services 通过 settings 实例读取 (不再通过 os.getenv 或 DB Config)
    ↓
DB Config 表 → 仅用于运行时 UI 可调参数 (download_dir, max_concurrent 等)
```

### 任务

1. **扩展 `Settings` 类** (`backend/app/core/config.py`)
   - 所有 SiliconFlow 相关配置统一用 `siliconflow_` 前缀
   - 新增字段: `siliconflow_stt_model`, `siliconflow_api_key` (已有), `siliconflow_base_url` (已有)
   - 移除不再需要的 `whisper_model`/`whisper_language` (改用 DB)

2. **消除 DB Config 中的 API 密钥**
   - 删除 `config_seeder.py` 中的 `translation_api_key`, `siliconflow_api_key` 等密钥类配置
   - DB Config 表只保留 UI 可调参数: `download_dir`, `max_concurrent_downloads`, `max_resolution`, `scan_*`, `whisper_*`, `dubbing_*`, `publish_*`

3. **统一所有 service 的配置读取**
   - `tts_new/siliconflow_provider.py`: 从 `settings.siliconflow_api_key` + `settings.siliconflow_base_url` 读取
   - `transcriber/siliconflow_provider.py`: 同上
   - `voice_cloner/siliconflow_provider.py`: 同上
   - `siliconflow/client.py`: 从 `settings` 读取, 不再 `os.getenv`
   - `translation_service.py`: 从 `settings` 读取 (若保留)
   - `title_generator.py`: 从 `settings` 读取

4. **修复 DB key 命名不一致**
   - 前端 SettingsView 中的 `siliconflow_api_key` → 统一用 `siliconflow_api_key`
   - `api/config.py` 测试端点 → 统一用 `settings.siliconflow_api_key`
   - `config_seeder.py` 移除重复的 `whisper_model` 键
   - 移除 `.env` 中的 `SILICONFLOW_STT_MODEL`/`SILICONFLOW_TTS_MODEL`/`SILICONFLOW_TRANSLATE_MODEL` (改用 settings 统一字段)

5. **清理 unused `.env` 变量**
   - 保留: `SILICONFLOW_API_KEY`, `SILICONFLOW_BASE_URL`
   - 删除: `SILICONFLOW_STT_MODEL`, `SILICONFLOW_TTS_MODEL`, `SILICONFLOW_TRANSLATE_MODEL`
   - 模型选择移到 DB Config (UI 可调)

---

## Phase 2: API 层清理与规范化

### 问题
- `dubbing.py` (旧) 和 `dub.py` (新) 两套配音 API 并存
- 错误处理 4 种不同模式
- 部分文件返回裸 ORM 对象, 部分用 Pydantic 模型
- `transcription.py`/`voice_clone.py` 有无用的 `db` 参数

### 任务

1. **删除 `dubbing.py` (旧版配音 API)**
   - 从 `router.py` 移除 `/api/dubbing` 路由注册
   - 检查前端是否仍调用 `/api/dubbing` → `frontend/src/api/index.ts` 中有 `dubbingApi.dub()`
   - 将前端调用切换到 `/api/dub`

2. **删除 `upload.py` (旧版上传 API)**
   - 已被 `/api/publish` 取代
   - 检查是否有残留调用

3. **清理无效 `db` 参数**
   - `transcription.py` / `voice_clone.py` → 移除未使用的 `db: AsyncSession = Depends(get_db)`

4. **统一错误处理模式**
   - 所有 API 文件统一: `try/except` + `HTTPException(status_code, detail=str(e))`
   - 中文错误消息统一 (面向中文用户)

5. **统一响应格式**
   - 所有端点使用 Pydantic `response_model`
   - 不再返回裸 ORM 对象

6. **统一状态引用**
   - 全项目使用 `app.models.enums` 中的枚举 (VideoStatus, TaskStatus, TaskType, PublishStatus, PublishPlatform)
   - 不再使用字符串状态

---

## Phase 3: Service 层去冗余

### 问题
- `tts_service.py` + `translation_service.py` = 仅被 archived 代码引用 = 死代码
- `_archived/dubbing_service_old.py` = 无人引用
- `siliconflow/tts.py` 与 `tts_new/siliconflow_provider.py` 功能重复
- `publish/bilibili.py` (Playwright 方案) 仅被测试引用, 生产用 `sau_bilibili.py`

### 任务

1. **删除死代码**
   - 删除 `backend/app/services/tts_service.py`
   - 删除 `backend/app/services/translation_service.py`
   - 删除 `backend/app/services/_archived/` 整个目录
   - 删除 `backend/app/services/publish/bilibili.py` (Playwright 版)
   - 删除 `backend/app/services/whisper_service.py`? → **保留**: scheduler 和 pipeline 仍直接使用

2. **合并 TTS 实现**
   - 保留 `tts_new/siliconflow_provider.py` (有完整 provider 模式)
   - 将 `siliconflow/tts.py` 中的 tenacity 重试逻辑合并到 provider
   - 删除 `siliconflow/tts.py`
   - scheduler.py 中 `from app.services.siliconflow.tts import synthesize_speech` → 改为使用 `TTSService`

3. **保留但标记**
   - `siliconflow/client.py`: 仍被 scheduler、title_generator、publish/title_translate、translate.py 使用 → 保留
   - `siliconflow/translate.py`: 仍被 scheduler、pipeline 使用 → 保留

---

## Phase 4: Social-Auto-Upload 清理

### 问题
- 两个小红书上传器 (`xhs_uploader/` + `xiaohongshu_uploader/`)
- `conf.py` 和 `conf.example.py` 完全相同
- 多个未使用的上传器模块
- 通过 `sys.path` 注入集成 (脆弱)

### 任务

1. **删除重复的小红书上传器**
   - 确认哪个被实际使用 → 删除 `xhs_uploader/` (确认 xiaohongshu_uploader 是主用的)
   - 或合并两者

2. **分离 `conf.py` 和 `conf.example.py`**
   - `conf.example.py` 保留占位符, `conf.py` 加入 `.gitignore`

3. **标记未使用的上传器**
   - `ks_uploader/`, `tencent_uploader/`, `tk_uploader/`, `baijiahao_uploader/`, `youtube_uploader/`
   - 保留代码但不加载到主流程
   - 在文档中说明可用但未集成的平台

---

## Phase 5: 前端清理

### 问题
- 4 个视图通过路由重定向隐藏但仍占用代码
- 状态/步骤标签在 3 处重复定义
- Store 绕过类型化 API 层直接调用 `api.get()`
- 硬编码 `baseURL: '/api'` 和 CORS origin

### 任务

1. **清理不可达视图**
   - `VideosView.vue`: 路由已重定向到 `/dashboard`, 删除
   - `PlatformLoginView.vue`: 路由已重定向到 `/dashboard`, 删除
   - 注意: `ChannelsView.vue` 和 `PublishHistoryView.vue` 仍在 TasksView 中懒加载使用

2. **抽取共享常量**
   - 创建 `frontend/src/constants.ts`
   - 统一: `TASK_STEP_LABELS`, `STATUS_META`, `STATUS_LABELS`

3. **Store 使用类型化 API**
   - `configStore.ts`: `api.get('/config')` → `configApi.list()`
   - `taskStore.ts`: 直接调用 → 通过 `api/index.ts` 中的命名空间函数
   - `videoStore.ts`: 同上

4. **配置化前端 API**
   - 添加 `VITE_API_BASE_URL` 支持
   - CORS origin 从环境变量读取

---

## Phase 6: 数据库清理

### 任务

1. **清理 Config 表**
   - 移除重复/无用的配置键
   - 统一命名规范: `snake_case` 全部小写

2. **Alembic 迁移**
   - 创建新的 migration 清理 Config 表数据
   - 不改变 schema, 只做数据迁移

---

## 删除/修改清单

### 删除文件

| 文件 | 原因 |
|------|------|
| `backend/app/services/tts_service.py` | 死代码 (edge-tts, 仅 archived 引用) |
| `backend/app/services/translation_service.py` | 死代码 (仅 archived 引用) |
| `backend/app/services/_archived/dubbing_service_old.py` | 已归档, 无人引用 |
| `backend/app/services/_archived/__init__.py` | 已归档 |
| `backend/app/services/publish/bilibili.py` | 仅测试引用, 生产用 sau_bilibili |
| `backend/app/services/siliconflow/tts.py` | 与 tts_new/siliconflow_provider.py 重复 |
| `backend/app/api/dubbing.py` | 旧版配音 API, 被 dub.py 取代 |
| `backend/app/api/upload.py` | 旧版上传 API, 被 publish.py 取代 |
| `frontend/src/views/VideosView.vue` | 路由已重定向, 不可达 |
| `frontend/src/views/PlatformLoginView.vue` | 路由已重定向, 不可达 |
| `social-auto-upload/conf.py` | 应为 .gitignore (敏感), 保留 conf.example.py |
| `social-auto-upload/uploader/xhs_uploader/` | 重复实现, 保留 xiaohongshu_uploader |

### 修改文件

| 文件 | 改动 |
|------|------|
| `backend/app/core/config.py` | 扩展 Settings 类, 添加所有模型字段 |
| `backend/app/services/config_seeder.py` | 移除密钥配置, 修复重复键 |
| `backend/app/services/siliconflow/client.py` | 从 settings 读取而非 os.getenv |
| `backend/app/services/tts_new/siliconflow_provider.py` | 合并 tenacity 重试, 从 settings 读取 URL |
| `backend/app/services/transcriber/siliconflow_provider.py` | 从 settings 读取基础 URL |
| `backend/app/services/voice_cloner/siliconflow_provider.py` | 从 settings 读取基础 URL |
| `backend/app/services/title_generator.py` | 从 settings 读取模型 |
| `backend/app/api/router.py` | 移除 dubbing/upload 路由 |
| `backend/app/api/config.py` | 简化测试端点 |
| `backend/app/api/transcription.py` | 移除无用 db 参数 |
| `backend/app/api/voice_clone.py` | 移除无用 db 参数 |
| `backend/app/main.py` | 清理过时注释 |
| `frontend/src/api/index.ts` | 移除 dubbingApi (用 dubApi) |
| `frontend/src/router/index.ts` | 移除 VideosView/PlatformLoginView 路由 |
| `frontend/src/stores/configStore.ts` | 使用 configApi.list() |
| `frontend/src/stores/taskStore.ts` | 使用命名空间 API |
| `frontend/src/stores/videoStore.ts` | 使用命名空间 API |
| `frontend/src/views/DashboardView.vue` | 使用共享常量 |
| `frontend/src/views/TasksView.vue` | 使用共享常量 |

---

## 执行顺序

```
Phase 1 (配置统一) → Phase 2 (API 清理) → Phase 3 (Service 清理) → Phase 4 (SAU 清理) → Phase 5 (前端清理) → Phase 6 (DB 清理)
```

每完成一个 Phase 运行测试确保不引入回归。

## 成功标准

1. 所有测试通过 (`pytest backend/tests/ -x -q`)
2. 前端构建成功 (`npm run build`)
3. `SILICONFLOW_API_KEY` 在 `.env` 中配置后, API 测试端点返回成功
4. 前端 Settings 页保存 API Key 后, TTS/翻译/转录均可用
5. 删除的旧文件不再被任何代码引用
