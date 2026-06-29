@echo off
chcp 65001 >nul
title VidDub
cd /d "%~dp0"

if not exist "frontend\node_modules" (
    echo [FAIL] frontend\node_modules not found, run 'npm install' first
    pause
    exit /b 1
)

echo.
echo [*] Killing old processes on port 8000 5173...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 "') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173 "') do taskkill /f /pid %%a >nul 2>&1

echo [*] Starting backend http://localhost:8000
REM Use start_server.py launcher instead of direct uvicorn CLI because:
REM   1. --loop none is rejected by uvicorn CLI validator (only auto/asyncio/uvloop accepted)
REM   2. Programmatic loop="none" skips uvicorn's SelectorEventLoopPolicy override on Windows
REM   3. ProactorEventLoopPolicy (set in start_server.py + main.py) is preserved for
REM      create_subprocess_exec() used by patchright/Playwright to launch Chromium.
start /min cmd /c "cd /d %~dp0backend && python start_server.py"

echo [*] Starting frontend http://localhost:5173
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
