# 常见问题排查

> 启动 / 配音 / 发布过程中遇到问题先看这里。按问题类型分组。

---

## 1. API Key 与 SiliconFlow

### 1.1 报错 `SILICONFLOW_API_KEY is required` / 启动即退出

**原因**：`backend/.env` 缺少 `SILICONFLOW_API_KEY`，或 `.env` 文件本身不存在。

**排查**：
```bash
# 确认文件存在
ls backend/.env

# 确认 key 不为空
grep SILICONFLOW_API_KEY backend/.env
```

**修复**：
1. 申请 key：https://cloud.siliconflow.cn/account/ak
2. 编辑 `backend/.env`：`SILICONFLOW_API_KEY=sk_xxx`
3. 重启服务

### 1.2 报错 401 / 403 — API key 无效

**原因**：key 错填 / 过期 / 没充值。

**修复**：
- 登录 SiliconFlow 控制台确认 key 状态、账户余额
- Web UI → Settings → SiliconFlow tab → 点"测试连通性"
- 改完 `.env` 后**必须重启 uvicorn**（pydantic-settings 只在启动时读）

### 1.3 报错 429 — 限流

**原因**：SiliconFlow 免费档 / 套餐请求频率上限。

**症状**：日志看到 `HTTP 429: rate limit`，任务进入 `failed`。

**修复**：
- 短期：等待 60s 重试（`POST /api/dub/{id}/resume` 或 Web UI 重试按钮）
- 长期：
  1. 升级 SiliconFlow 套餐
  2. 降低并发：Web UI 把 `max_concurrent_downloads` 改为 1，配置文件层面 TTS 并发固定 `Semaphore(3)`，可在 `services/dubbing/pipeline.py` 调小
  3. 错峰执行（夜间）
- 看日志：`backend/data/*.log` 或 uvicorn 控制台输出

### 1.4 翻译质量太差 / 不符合中文表达

**原因**：模型上下文不够 / 默认 prompt 太简。

**修复**：
- Web UI 把 `translation_context_window` 从 2 调到 4
- 修改 `services/siliconflow/translate.py` 中的 SYSTEM_PROMPT（按你的视频领域定制，如"技术教学视频"）
- 单段翻译不准 → SubtitleEditorView 行内重新翻译按钮

---

## 2. Whisper 模型下载

### 2.1 模型下载极慢 / 卡住

**原因**：默认从 HuggingFace CDN 下载，国内访问慢。

**修复方案 A — 用镜像源**：

```bash
# Linux/macOS
export HF_ENDPOINT=https://hf-mirror.com
# Windows PowerShell
$env:HF_ENDPOINT="https://hf-mirror.com"

# 再跑 setup.sh / setup.ps1 的预下载步骤
backend/venv/bin/python -c "import whisper; whisper.load_model('tiny')"
```

**修复方案 B — 手动下载放到缓存目录**：

1. 浏览器打开 https://hf-mirror.com/openai/whisper-tiny（或 base/small/medium）
2. 下载 `pytorch_model.bin`（tiny ≈ 75MB，base ≈ 145MB）
3. 放到：
   - **Windows**：`C:\Users\<你的用户名>\.cache\whisper\whisper-tiny.pt`
   - **Linux/macOS**：`~/.cache/whisper/whisper-tiny.pt`

**修复方案 C — 改用更小模型**：

```bash
# .env
WHISPER_MODEL=tiny     # 或 base（比 small/medium 小很多）
```

### 2.2 报错 `FileNotFoundError: ... whisper*.pt`

**原因**：模型文件被删 / 路径权限问题。

**修复**：重跑 `python -c "import whisper; whisper.load_model('tiny')"`，会重新下载。

### 2.3 转写质量差（识别错字多）

**原因**：`tiny` 模型精度有限。

**修复**：
- 改用 `base` 或 `small`（更准，但更慢 / 更大）
- 在 Web UI Settings → STT tab 改
- 或 `.env`: `WHISPER_MODEL=base`
- 重启服务

### 2.4 转写耗时极长（视频很短但跑了几十分钟）

**原因**：CPU-only 模式 + 默认模型偏大。

**修复**：
- 改 `WHISPER_MODEL=tiny`
- 关闭其他 CPU 密集任务
- 如有 NVIDIA GPU，安装 CUDA 版 PyTorch（[pytorch.org](https://pytorch.org)），Whisper 会自动用 GPU

---

## 3. ffmpeg

### 3.1 报错 `FileNotFoundError: ffmpeg` / `ffmpeg not found`

**原因**：ffmpeg 没装 / 不在 PATH。

**修复**：

**Windows**：
1. 下载：https://www.gyan.dev/ffmpeg/builds/ → `ffmpeg-release-essentials.zip`
2. 解压到 `C:\ffmpeg\`
3. 把 `C:\ffmpeg\bin` 加入系统 PATH：
   ```powershell
   # 永久加入（管理员权限）
   [Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\ffmpeg\bin", "Machine")
   ```
4. 重启 PowerShell，验证：`ffmpeg -version`

**Linux (Debian/Ubuntu)**：
```bash
sudo apt update && sudo apt install -y ffmpeg
```

**macOS**：
```bash
brew install ffmpeg
```

### 3.2 ffmpeg 命令失败但报错信息不清晰

**排查**：在 `backend/data/*.log` 或 uvicorn 控制台找 `[ffmpeg]` 前缀的完整 stderr 输出。

常见原因：
- 视频损坏 → 重新下载
- 磁盘满 → 清理 `backend/downloads/`
- 编解码器缺失 → 装 `gpl` 版 ffmpeg（含全部 codec）

---

## 4. Playwright（平台登录/发布）

### 4.1 报错 `Executable doesn't exist at .../chromium-*/chrome-win/...`

**原因**：Playwright Chromium 没装。

**修复**：
```bash
# 在 venv 内
backend/venv/Scripts/python -m playwright install chromium
# Linux: backend/venv/bin/python -m playwright install chromium
```

setup.ps1 / setup.sh 默认会装，加 `-SkipPlaywright` 才会跳过。

### 4.2 Linux 服务器启动 Playwright 失败 — 缺依赖库

**症状**：`error while loading shared libraries: libnss3.so` 等。

**修复**：
```bash
sudo playwright install-deps chromium
# 或手动
sudo apt install -y libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2
```

### 4.3 Linux 服务器无图形界面 — Playwright 启动失败

**原因**：西瓜视频登录/发布用 **headed** 模式（D6-03），需要 X display。

**修复方案 A — xvfb 虚拟显示**：
```bash
sudo apt install -y xvfb
xvfb-run -a ./start.sh
```

**修复方案 B — 改 headless（不推荐，风控敏感）**：

修改 `app/services/platform/ixigua.py`，`chromium.launch(headless=True)`。容易被识别为机器人。

**修复方案 C — 仅使用哔哩哔哩**（哔哩哔哩登录走 HTTP QR API，不需要浏览器）

### 4.4 显存不足 / GPU 报错

**原因**：本工具只用 Whisper 用 GPU，Playwright Chromium 用 CPU 渲染。如显存确实不足，关掉其它 GPU 程序。

### 4.5 哔哩哔哩二维码不显示

**原因**：`qrcode` Python 包没装。

**修复**：
```bash
backend/venv/Scripts/pip install qrcode>=7.4
```

setup 脚本已包含，手动装 requirements 时漏装会出现。

---

## 5. Windows 特定问题

### 5.1 路径含中文 → 各种莫名错误

**症状**：`SyntaxError` / `FileNotFoundError` / `UnicodeDecodeError`。

**原因**：Python / ffmpeg / Playwright 在含中文路径下偶发解析问题。

**修复**：把项目放到**全英文**路径，例如 `C:\dev\viddub\`（不要 `C:\Users\小明\Desktop\...`）。

### 5.2 PowerShell 执行策略阻止脚本运行

**症状**：`.\setup.ps1 cannot be loaded because running scripts is disabled on this system`

**修复**：
```powershell
# 仅当前用户允许本地脚本
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# 或一次性绕过
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

### 5.3 venv 创建失败 — `python -m venv venv` 报错

**原因**：Python 安装时没勾选 "Add Python to PATH"，或 `venv` 模块缺失。

**修复**：
- 重装 Python 3.10+，勾选 "Add Python to PATH"
- 自定义安装勾选 "tcl/tk and IDLE" 和 "py launcher"
- 验证：`python -m venv --help` 应显示帮助

### 5.4 行尾符问题（git checkout 后 .sh 脚本无法运行）

**原因**：Windows git 默认 CRLF，Linux 不能跑 CRLF .sh。

**修复**：
```bash
# 在 Linux 上转换
dos2unix setup.sh start.sh

# 或在 git 配置（仅本仓库）
git config core.autocrlf false
```

---

## 6. 数据库

### 6.1 SQLite 锁 — `database is locked`

**原因**：SQLite 默认串行写，多请求并发写时偶发锁。

**修复**：
- 已启用 WAL 模式（如未启用，执行 `PRAGMA journal_mode=WAL;`）
- 重启 uvicorn 清理死连接
- 长期方案：限制并发任务数 `max_concurrent_downloads=1`
- 终极方案：换 PostgreSQL（修改 `.env` 的 `DATABASE_URL`）

### 6.2 数据库迁移失败 — `alembic upgrade head` 报错

**原因**：
- 数据库版本与代码迁移版本不匹配
- `backend/data/viddub.db` 文件被锁
- 迁移文件冲突

**修复**：
```bash
cd backend

# 查看当前版本
venv/Scripts/python -m alembic current

# 查看 history
venv/Scripts/python -m alembic history

# 回到上一个版本（危险！先备份）
cp data/viddub.db data/viddub.db.bak
venv/Scripts/python -m alembic downgrade -1

# 重新 upgrade
venv/Scripts/python -m alembic upgrade head
```

### 6.3 数据库重置（清空重来）

**警告**：会丢失所有视频/任务/配置/登录态！

```bash
cd backend
# 停止 uvicorn
rm data/viddub.db data/*.db-wal data/*.db-shm 2>/dev/null
venv/Scripts/python -m alembic upgrade head   # 重新建表
# 重启 uvicorn 会自动 seed 默认配置
```

---

## 7. 平台发布（Phase 7）

### 7.1 上传失败 — 平台风控

**症状**：发布到 `uploading` 阶段失败，平台端日志显示风控拦截。

**原因**：
- 发布频率过高（同 IP 短时间多次发布）
- 标题/描述含敏感词
- 视频内容触发审核

**修复**：
- 降频：每天最多 2-3 个视频
- 改标题：Web UI 或 Settings 把默认标签 `搬运,英语学习` 改成更具体的内容
- 人工干预：登录 web 端创作者中心手动审核
- 等待：平台审核通过后再发新视频

### 7.2 标题选择器失效 — Playwright 找不到输入框

**原因**：平台前端 DOM 改版。

**修复**：
- 升级到最新版（git pull）
- 失败时会自动保存截图到 `backend/data/screenshots/`，对照截图修改 `services/publish/bilibili.py` 或 `ixigua.py` 的选择器
- 临时方案：关闭自动发布，手动上传

### 7.3 登录态过期频繁

**症状**：登录后几小时就提示重新登录。

**修复**：
- 检查 `backend/data/login/{platform}_storage_state.json` 文件权限（chmod 600）
- 不要同时在不同设备登录同账号（互踢）
- 浏览器检测到 Playwright → 把 user-agent 改成真实浏览器（编辑 `platform/base.py` 的 launch args）

---

## 8. 性能问题

### 8.1 整个配音流程很慢

**典型耗时**（10 分钟英文视频，CPU i7-12700H + 32GB RAM + Whisper tiny）：

| 步骤 | 耗时 | 占比 |
|------|------|------|
| 下载 | 30-60s | 10% |
| 提取音频 | 5s | 2% |
| Whisper STT (CPU) | 60-120s | 25% |
| 翻译 (SiliconFlow) | 20-40s | 8% |
| TTS (SiliconFlow，串行段数 × 5s) | 200-400s | 50% |
| ffmpeg 合成 | 20-30s | 5% |

**优化**：
- 装GPU + CUDA 版 PyTorch → Whisper 提速 5-10x
- 升级 SiliconFlow 套餐 → TTS 限流降低
- 短视频优先（< 10 分钟）

### 8.2 磁盘占用快速增长

**清理**：
```bash
# 旧视频成品（保留最近 30 天）
find backend/downloads/ -mtime +30 -type f -delete

# 临时音频中间文件
find backend/downloads/ -name "*.wav" -mtime +1 -delete
find backend/downloads/ -name "dubbing_segment_*.mp3" -mtime +1 -delete

# SQLite WAL（停服时）
sqlite3 backend/data/viddub.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

### 8.3 内存占用高

- Whisper 模型常驻 ~500MB（base 模型）
- Playwright Chromium ~300-500MB（仅登录/发布时）
- 建议至少 8GB RAM

---

## 9. 调试技巧

### 9.1 启用详细日志

```bash
# 启动时加 --log-level debug
cd backend
venv/Scripts/uvicorn app.main:app --reload --log-level debug
```

### 9.2 单步执行管线

```bash
# 用 CLI 而非 API，便于看输出
cd backend
venv/Scripts/python -m app.cli dub "https://www.youtube.com/watch?v=XXXX"
```

### 9.3 单独测试某段

```python
# 进入 venv
backend/venv/Scripts/python
>>> from app.services.siliconflow.client import SiliconFlowClient
>>> c = SiliconFlowClient()
>>> # ...
```

### 9.4 看 WebSocket 消息

浏览器 DevTools → Network → WS → 选 `/ws` 连接 → Messages tab 可看到所有事件实时推送。

---

## 10. 获取帮助

- 查看对应 Phase 的 SUMMARY：`.planning/phases/NN-xxx/NN-01-SUMMARY.md`
- 查看架构图：[docs/ARCHITECTURE.md](ARCHITECTURE.md)
- 查看配置项：[docs/CONFIGURATION.md](CONFIGURATION.md)
- API 调试：http://localhost:8000/docs

---

*本文档对应 Phase 10 (v2.0.10) · 最后更新：2026-06-22*
