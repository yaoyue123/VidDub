<#
.SYNOPSIS
    VidDub 一键环境初始化脚本 (Windows PowerShell)
.DESCRIPTION
    - 检查 Python / Node / ffmpeg / yt-dlp 依赖
    - 创建 backend/venv 并安装 Python 依赖
    - 安装 Playwright Chromium
    - 安装 frontend npm 依赖
    - 预下载 Whisper tiny 模型
    - 运行 Alembic 数据库迁移
.NOTES
    使用方式：
        PS> .\setup.ps1
    可选参数：
        -WhisperModel tiny|base|small|medium   (默认: tiny)
        -SkipFrontend                          (跳过 npm install)
        -SkipPlaywright                        (跳过 playwright install chromium)
#>

[CmdletBinding()]
param(
    [ValidateSet("tiny","base","small","medium")]
    [string]$WhisperModel = "tiny",
    [switch]$SkipFrontend,
    [switch]$SkipPlaywright
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend     = Join-Path $ProjectRoot "backend"
$Frontend    = Join-Path $ProjectRoot "frontend"

function Write-Step([string]$msg) { Write-Host "`n[*] $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Die([string]$msg) {
    Write-Host "[FAIL] $msg" -ForegroundColor Red
    exit 1
}

Write-Host "==================================" -ForegroundColor White
Write-Host " VidDub Setup (Windows)" -ForegroundColor White
Write-Host "==================================" -ForegroundColor White

# ─────────────────────────────────────────────────────────
# 1. 依赖检查
# ─────────────────────────────────────────────────────────
Write-Step "检查系统依赖..."

# Python >= 3.10
try {
    $pyVersion = (& python --version) 2>&1
    if ($pyVersion -match "Python (\d+)\.(\d+)") {
        $pyMajor = [int]$Matches[1]; $pyMinor = [int]$Matches[2]
        if ($pyMajor -lt 3 -or ($pyMajor -eq 3 -and $pyMinor -lt 10)) {
            Die "Python 版本过低: $pyVersion (需要 3.10+)"
        }
        Write-Ok "Python: $pyVersion"
    } else { Die "无法识别 python 版本: $pyVersion" }
} catch { Die "未找到 python，请安装 Python 3.10+ 并加入 PATH" }

# Node >= 18
try {
    $nodeVersion = (& node --version) 2>&1
    if ($nodeVersion -match "v(\d+)") {
        if ([int]$Matches[1] -lt 18) { Die "Node 版本过低: $nodeVersion (需要 18+)" }
        Write-Ok "Node: $nodeVersion"
    } else { Die "无法识别 node 版本: $nodeVersion" }
} catch { Die "未找到 node，请安装 Node.js 18+ 并加入 PATH" }

# npm
try { $npmV = (& npm --version) 2>&1; Write-Ok "npm: $npmV" }
catch { Die "未找到 npm，请确认 Node.js 完整安装" }

# ffmpeg
try {
    $ff = (& ffmpeg -version) 2>&1 | Select-Object -First 1
    if ($LASTEXITCODE -eq 0) { Write-Ok "ffmpeg: $ff" }
    else { Die "ffmpeg 不可用 (exit $LASTEXITCODE)" }
} catch { Die "未找到 ffmpeg，请安装并加入 PATH (https://www.gyan.dev/ffmpeg/builds/)" }

# yt-dlp
try {
    $ytdlp = (& yt-dlp --version) 2>&1 | Select-Object -First 1
    if ($LASTEXITCODE -eq 0) { Write-Ok "yt-dlp: $ytdlp" }
    else { Write-Warn "yt-dlp 不可用 — pip 安装时会自动带上" }
} catch { Write-Warn "yt-dlp 未在 PATH (将在 pip install 时一并安装)" }

# ─────────────────────────────────────────────────────────
# 2. 创建 venv + pip install
# ─────────────────────────────────────────────────────────
Write-Step "创建 Python 虚拟环境 backend/venv/ ..."
$VenvPython = Join-Path $Backend "venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Push-Location $Backend
    try {
        & python -m venv venv
        if ($LASTEXITCODE -ne 0) { Die "创建 venv 失败" }
        Write-Ok "venv 创建完成"
    } finally { Pop-Location }
} else {
    Write-Ok "venv 已存在，跳过创建"
}

Write-Step "安装 Python 依赖 (requirements.txt) ..."
& $VenvPython -m pip install --upgrade pip wheel | Out-Null
& $VenvPython -m pip install -r (Join-Path $Backend "requirements.txt")
if ($LASTEXITCODE -ne 0) { Die "pip install requirements.txt 失败" }
Write-Ok "Python 依赖安装完成"

# ─────────────────────────────────────────────────────────
# 3. Playwright Chromium
# ─────────────────────────────────────────────────────────
if (-not $SkipPlaywright) {
    Write-Step "安装 Playwright Chromium (用于平台登录/发布) ..."
    & $VenvPython -m playwright install chromium
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "playwright install chromium 失败 — 平台登录/发布将不可用，其它功能不受影响"
    } else {
        Write-Ok "Playwright Chromium 安装完成"
    }
} else {
    Write-Warn "已跳过 Playwright 安装 (-SkipPlaywright)"
}

# ─────────────────────────────────────────────────────────
# 4. Frontend npm install
# ─────────────────────────────────────────────────────────
if (-not $SkipFrontend) {
    Write-Step "安装前端 npm 依赖 ..."
    Push-Location $Frontend
    try {
        & npm install
        if ($LASTEXITCODE -ne 0) { Die "npm install 失败" }
        Write-Ok "前端依赖安装完成"
    } finally { Pop-Location }
} else {
    Write-Warn "已跳过前端依赖安装 (-SkipFrontend)"
}

# ─────────────────────────────────────────────────────────
# 5. 预下载 Whisper 模型
# ─────────────────────────────────────────────────────────
Write-Step "预下载 Whisper 模型 ($WhisperModel) ..."
# 这一步会下载到 ~\.cache\whisper\ ，避免运行时首次下载卡顿
& $VenvPython -c "import whisper; m = whisper.load_model('$WhisperModel'); print('Whisper model loaded:', m.device)"
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Whisper 模型预下载失败 — 首次运行时会重试，建议检查网络/镜像源"
} else {
    Write-Ok "Whisper 模型 $WhisperModel 已就绪"
}

# ─────────────────────────────────────────────────────────
# 6. 数据库迁移
# ─────────────────────────────────────────────────────────
Write-Step "运行 Alembic 数据库迁移 ..."
Push-Location $Backend
try {
    & $VenvPython -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Alembic 迁移失败 — 请检查 backend/alembic/versions/ 与 backend/data/viddub.db 权限"
    } else {
        Write-Ok "数据库迁移完成"
    }
finally { Pop-Location }

# ─────────────────────────────────────────────────────────
# 7. 检查 .env 配置
# ─────────────────────────────────────────────────────────
$EnvFile = Join-Path $Backend ".env"
$EnvExample = Join-Path $Backend ".env.example"
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Warn "已从 .env.example 复制创建 backend/.env — 必须填入 SILICONFLOW_API_KEY 才能使用配音功能"
    } else {
        Write-Warn "未找到 backend/.env — 配音功能将无法启动"
    }
} else {
    Write-Ok "backend/.env 已存在"
}

# ─────────────────────────────────────────────────────────
# 8. 完成提示
# ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==================================" -ForegroundColor White
Write-Host " Setup 完成！" -ForegroundColor Green
Write-Host "==================================" -ForegroundColor White
Write-Host ""
Write-Host "下一步：" -ForegroundColor Cyan
Write-Host "  1. 编辑 backend/.env，填入 SILICONFLOW_API_KEY"
Write-Host "     申请地址: https://cloud.siliconflow.cn/account/ak"
Write-Host "  2. 启动服务："
Write-Host "       PS> .\start.ps1"
Write-Host "  3. 访问前端: http://localhost:5173"
Write-Host "  4. FastAPI 文档: http://localhost:8000/docs"
Write-Host ""
Write-Host "更多文档：" -ForegroundColor Cyan
Write-Host "  - README.md"
Write-Host "  - docs/CONFIGURATION.md"
Write-Host "  - docs/TROUBLESHOOTING.md"
Write-Host "  - docs/ARCHITECTURE.md"
Write-Host ""
