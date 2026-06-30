@echo off
chcp 65001 >nul
title VidDub
cd /d "%~dp0"

echo ========================================
echo   VidDub 一键启动
echo ========================================

:: ── 1. 检查 / 安装 uv ──
where uv >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [*] 未找到 uv，正在安装...
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; iex (irm https://astral.sh/uv/install.ps1)}"
    :: 刷新 PATH
    for /f "tokens=2*" %%a in ('reg query HKCU\Environment /v Path 2^>nul') do set "PATH=%%~b;%PATH%"
    where uv >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo [FAIL] uv 安装失败，请手动安装: https://docs.astral.sh/uv/
        pause
        exit /b 1
    )
    echo [OK] uv 已安装
)

:: ── 2. 安装后端依赖 + 创建 .venv ──
if not exist "backend\.venv" (
    echo [*] 安装后端依赖...
    cd backend
    uv sync --group dev
    if %ERRORLEVEL% neq 0 (
        echo [FAIL] 后端依赖安装失败
        pause
        exit /b 1
    )
    cd ..
    echo [OK] 后端依赖已安装
)

:: ── 3. 安装前端依赖 ──
if not exist "frontend\node_modules" (
    echo [*] 安装前端依赖...
    cd frontend
    npm install
    if %ERRORLEVEL% neq 0 (
        echo [FAIL] 前端依赖安装失败
        pause
        exit /b 1
    )
    cd ..
    echo [OK] 前端依赖已安装
)

:: ── 4. 复制 .env ──
if not exist "backend\.env" (
    if exist "backend\.env.example" (
        copy backend\.env.example backend\.env >nul
        echo [OK] 已创建 backend\.env（请编辑填入 SILICONFLOW_API_KEY）
    )
)

:: ── 5. Playwright Chromium ──
set "PLAYWRIGHT_DIR=%USERPROFILE%\AppData\Local\ms-playwright"
if not exist "%PLAYWRIGHT_DIR%" (
    echo [*] 安装 Playwright Chromium...
    cd backend
    uv run python -m playwright install chromium
    cd ..
    echo [OK] Playwright Chromium 已安装
)

:: ── 6. 数据库迁移 ──
echo [*] 执行数据库迁移...
cd backend
uv run alembic upgrade head
cd ..
echo [OK] 数据库迁移完成

:: ── 7. Kill 旧进程 ──
echo.
echo [*] 停止旧进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 "') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173 "') do taskkill /f /pid %%a >nul 2>&1

:: ── 8. 启动服务 ──
echo [*] 启动后端 http://localhost:8000
REM Use uv run + start_server.py launcher instead of direct uvicorn CLI because:
REM   1. --loop none is rejected by uvicorn CLI validator (only auto/asyncio/uvloop accepted)
REM   2. Programmatic loop="none" skips uvicorn's SelectorEventLoopPolicy override on Windows
REM   3. ProactorEventLoopPolicy (set in start_server.py + main.py) is preserved for
REM      create_subprocess_exec() used by patchright/Playwright to launch Chromium.
start /min cmd /c "cd /d %~dp0backend && uv run python start_server.py"

echo [*] 启动前端 http://localhost:5173
start /min cmd /c "cd /d %~dp0frontend && set PORT=5173 && npm run dev"

echo.
echo Frontend: http://localhost:5173
echo Backend:  http://localhost:8000
echo Swagger:  http://localhost:8000/docs
echo Close the min windows to stop.
echo.

timeout /t 4 >nul
start http://localhost:5173

pause
