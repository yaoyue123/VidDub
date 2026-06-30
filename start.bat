@echo off
chcp 65001 >nul
title VidDub
cd /d "%~dp0"

echo ========================================
echo   VidDub Startup
echo ========================================

:: ----- 1. check/install uv -----
where uv >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [*] installing uv...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; iex (irm https://astral.sh/uv/install.ps1)}"
    for /f "tokens=2*" %%a in ('reg query HKCU\Environment /v Path 2^>nul') do set "PATH=%%~b;%PATH%"
    where uv >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo [FAIL] uv install failed. manual: https://docs.astral.sh/uv/
        pause
        exit /b 1
    )
    echo [OK] uv ready
)

:: ----- 2. backend deps + .venv -----
if not exist "backend\.venv" (
    echo [*] installing backend deps...
    cd backend
    uv sync --group dev
    if %ERRORLEVEL% neq 0 (
        echo [FAIL] backend deps install failed
        pause
        exit /b 1
    )
    cd ..
    echo [OK] backend deps ready
)

:: ----- 3. frontend deps -----
if not exist "frontend\node_modules" (
    echo [*] installing frontend deps...
    cd frontend
    call npm install
    if %ERRORLEVEL% neq 0 (
        echo [FAIL] frontend deps install failed
        pause
        exit /b 1
    )
    cd ..
    echo [OK] frontend deps ready
)

:: ----- 4. .env -----
if not exist "backend\.env" (
    if exist "backend\.env.example" (
        copy backend\.env.example backend\.env >nul
        echo [OK] created backend\.env (edit to add SILICONFLOW_API_KEY)
    )
)

:: ----- 5. Playwright Chromium -----
set "PLAYWRIGHT_DIR=%USERPROFILE%\AppData\Local\ms-playwright"
if not exist "%PLAYWRIGHT_DIR%" (
    echo [*] installing Playwright Chromium...
    cd backend
    uv run python -m playwright install chromium
    cd ..
    echo [OK] Playwright Chromium ready
)

:: ----- 6. DB migration -----
echo [*] running DB migration...
cd backend
uv run python -m alembic upgrade head
cd ..
echo [OK] DB migration done

:: ----- 7. kill old processes -----
echo [*] stopping old processes...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 "') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173 "') do taskkill /f /pid %%a >nul 2>&1

:: ----- 8. start backend -----
echo [*] starting backend http://localhost:8000
start /min cmd /c "cd /d %~dp0backend && uv run python start_server.py"

:: ----- 9. start frontend -----
echo [*] starting frontend http://localhost:5173
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
