#Requires -Version 5.1
# setup.ps1 — VidDub 一键初始化脚本 (uv 版)
#
# 用法: .\setup.ps1
#
# 自动完成:
#   1. 检查/安装 uv (Python 包管理器)
#   2. uv sync 创建 .venv + 安装后端依赖
#   3. 安装 Playwright Chromium
#   4. 安装前端 npm 依赖
#   5. 复制 .env.example → .env（如不存在）
#   6. 执行数据库迁移

$ErrorActionPreference = "Stop"
$PROJECT_ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$BACKEND = Join-Path $PROJECT_ROOT "backend"
$FRONTEND = Join-Path $PROJECT_ROOT "frontend"

function Log($msg) { Write-Host "[*] $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "[✓] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }

Log "VidDub 环境初始化"

# ── 1. 检查 uv ──
$uv = Get-Command "uv" -ErrorAction SilentlyContinue
if (-not $uv) {
    Log "未找到 uv，正在安装..."
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";$env:Path"
    $uv = Get-Command "uv" -ErrorAction SilentlyContinue
    if (-not $uv) {
        Write-Host "[FAIL] uv 安装失败。请手动安装: https://docs.astral.sh/uv/" -ForegroundColor Red
        exit 1
    }
    Ok "uv 已安装"
} else {
    Ok "uv 已就绪 ($($uv.Source))"
}

# ── 2. 安装后端依赖 ──
Log "安装后端依赖..."
Set-Location $BACKEND
uv sync --group dev
if ($LASTEXITCODE -ne 0) { throw "uv sync 失败" }
Ok "后端依赖已安装"

# ── 3. 安装 Playwright Chromium ──
Log "检查 Playwright Chromium..."
$playwright_path = "$env:USERPROFILE\AppData\Local\ms-playwright"
if (-not (Test-Path $playwright_path)) {
    Log "安装 Playwright Chromium..."
    uv run python -m playwright install chromium
    Ok "Playwright Chromium 已安装"
} else {
    Ok "Playwright Chromium 已就绪"
}

# ── 4. 安装前端依赖 ──
Log "安装前端依赖..."
Set-Location $FRONTEND
npm install
if ($LASTEXITCODE -ne 0) { throw "npm install 失败" }
Ok "前端依赖已安装"

# ── 5. 复制 .env ──
$envFile = Join-Path $BACKEND ".env"
$envExample = Join-Path $BACKEND ".env.example"
if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Ok "已创建 backend\.env（请编辑填入 SILICONFLOW_API_KEY）"
    }
} else {
    Ok "backend\.env 已存在"
}

# ── 6. 数据库迁移 ──
Log "执行数据库迁移..."
Set-Location $BACKEND
uv run alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "数据库迁移失败" }
Ok "数据库迁移完成"

Set-Location $PROJECT_ROOT
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  VidDub 初始化完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "启动: .\start.bat" -ForegroundColor Cyan
Write-Host ""
