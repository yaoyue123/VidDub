<#
.SYNOPSIS
    You2Bili 一键启动脚本 (Windows)
.DESCRIPTION
    启动后端 uvicorn (端口 8000) + 前端 vite dev (端口 5173)。
    关闭本窗口或按 Ctrl+C 退出。
.NOTES
    使用方式：
        PS> .\start.ps1
    可选：
        -BackendPort 8000
        -FrontendPort 5173
#>

[CmdletBinding()]
param(
    [int]$BackendPort  = 8000,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend     = Join-Path $ProjectRoot "backend"
$Frontend    = Join-Path $ProjectRoot "frontend"
$VenvPython  = Join-Path $Backend "venv\Scripts\python.exe"
$VenvUvicorn = Join-Path $Backend "venv\Scripts\uvicorn.exe"

function Write-Step([string]$m) { Write-Host "`n[*] $m" -ForegroundColor Cyan }
function Die([string]$m) { Write-Host "[FAIL] $m" -ForegroundColor Red; exit 1 }

Write-Host "==================================" -ForegroundColor White
Write-Host " You2Bili 启动 (Windows)" -ForegroundColor White
Write-Host "==================================" -ForegroundColor White

# 检查 venv
if (-not (Test-Path $VenvPython)) {
    Die "未找到 backend/venv，请先运行 .\setup.ps1"
}

# 检查 .env
if (-not (Test-Path (Join-Path $Backend ".env"))) {
    Write-Host "[!] 未找到 backend/.env — 配音功能需要 SILICONFLOW_API_KEY" -ForegroundColor Yellow
}

# 检查 node_modules
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Die "未找到 frontend/node_modules，请先运行 .\setup.ps1"
}

Write-Step "启动后端 uvicorn (http://localhost:$BackendPort) ..."
$backendJob = Start-Job -ScriptBlock {
    param($VenvUvicorn, $Backend, $BackendPort)
    & $VenvUvicorn "app.main:app" `
        --host "127.0.0.1" --port $BackendPort --reload `
        --app-dir "$Backend"
} -ArgumentList $VenvUvicorn, $Backend, $BackendPort

Write-Step "启动前端 vite dev (http://localhost:$FrontendPort) ..."
$frontendJob = Start-Job -ScriptBlock {
    param($Frontend, $FrontendPort)
    Push-Location $Frontend
    try {
        $env:PORT = "$FrontendPort"
        & npm run dev
    } finally { Pop-Location }
} -ArgumentList $Frontend, $FrontendPort

Write-Host ""
Write-Host "==================================" -ForegroundColor Green
Write-Host " 服务已启动" -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Green
Write-Host ""
Write-Host "前端:    http://localhost:$FrontendPort" -ForegroundColor Cyan
Write-Host "后端 API: http://localhost:$BackendPort" -ForegroundColor Cyan
Write-Host "Swagger: http://localhost:$BackendPort/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "按 Ctrl+C 停止所有服务。日志在下方实时输出..." -ForegroundColor Yellow
Write-Host ""

try {
    # 实时拉取 job 输出直到用户中断
    while ($true) {
        Receive-Job $backendJob -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Host "[backend] $_" -ForegroundColor DarkGray
        }
        Receive-Job $frontendJob -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Host "[frontend] $_" -ForegroundColor DarkCyan
        }
        Start-Sleep -Milliseconds 500

        if ($backendJob.State -eq "Failed" -or $frontendJob.State -eq "Failed") {
            Write-Host "[!] 服务异常退出" -ForegroundColor Red
            break
        }
    }
} finally {
    Write-Host "`n[*] 停止服务..." -ForegroundColor Cyan
    Stop-Job $backendJob -ErrorAction SilentlyContinue
    Stop-Job $frontendJob -ErrorAction SilentlyContinue
    Remove-Job $backendJob -Force -ErrorAction SilentlyContinue
    Remove-Job $frontendJob -Force -ErrorAction SilentlyContinue
}
