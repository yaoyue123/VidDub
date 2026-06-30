#!/usr/bin/env bash
# VidDub 一键启动脚本 (Linux / macOS)
# 自动完成环境初始化 + 启动服务
#
# 用法: ./start.sh [backend_port] [frontend_port]

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$PROJECT_ROOT/backend"
FRONTEND="$PROJECT_ROOT/frontend"

BACKEND_PORT="${1:-8000}"
FRONTEND_PORT="${2:-5173}"

C_CYAN="\033[36m"; C_GREEN="\033[32m"; C_YELLOW="\033[33m"; C_RED="\033[31m"; C_RESET="\033[0m"

log()  { echo -e "${C_CYAN}[*]${C_RESET} $1"; }
ok()   { echo -e "${C_GREEN}[✓]${C_RESET} $1"; }
warn() { echo -e "${C_YELLOW}[!]${C_RESET} $1"; }
fail() { echo -e "${C_RED}[FAIL]${C_RESET} $1"; exit 1; }

echo "=================================="
echo " VidDub 启动"
echo "=================================="

# ── 1. 检查/安装 uv ──
if ! command -v uv &>/dev/null; then
    log "未找到 uv，正在安装..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
    command -v uv &>/dev/null || fail "uv 安装失败。请手动安装: https://docs.astral.sh/uv/"
    ok "uv 已安装"
fi

# ── 2. 安装后端依赖 + 创建 .venv ──
if [ ! -d "$BACKEND/.venv" ]; then
    log "安装后端依赖..."
    cd "$BACKEND"
    uv sync --group dev
    cd "$PROJECT_ROOT"
    ok "后端依赖已安装"
fi

# ── 3. 安装前端依赖 ──
if [ ! -d "$FRONTEND/node_modules" ]; then
    log "安装前端依赖..."
    cd "$FRONTEND"
    npm install
    cd "$PROJECT_ROOT"
    ok "前端依赖已安装"
fi

# ── 4. 复制 .env ──
if [ ! -f "$BACKEND/.env" ]; then
    if [ -f "$BACKEND/.env.example" ]; then
        cp "$BACKEND/.env.example" "$BACKEND/.env"
        ok "已创建 backend/.env（请编辑填入 SILICONFLOW_API_KEY）"
    fi
fi

# ── 5. Playwright Chromium ──
PLAYWRIGHT_DIR="$HOME/.cache/ms-playwright"
if [ ! -d "$PLAYWRIGHT_DIR" ] || [ -z "$(ls -A "$PLAYWRIGHT_DIR" 2>/dev/null)" ]; then
    log "安装 Playwright Chromium..."
    cd "$BACKEND"
    uv run python -m playwright install chromium
    cd "$PROJECT_ROOT"
    ok "Playwright Chromium 已安装"
fi

# ── 6. 数据库迁移 ──
log "执行数据库迁移..."
cd "$BACKEND"
uv run alembic upgrade head
cd "$PROJECT_ROOT"
ok "数据库迁移完成"

# ── 7. 启动服务 ──
cleanup() {
    echo -e "\n${C_CYAN}[*] 停止所有服务...${C_RESET}"
    [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null || true
    [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo -e "\n${C_CYAN}[*] 启动后端 uvicorn (http://localhost:$BACKEND_PORT) ...${C_RESET}"
(
    cd "$BACKEND"
    uv run uvicorn app.main:app \
        --host "127.0.0.1" --port "$BACKEND_PORT" --reload
) &
BACKEND_PID=$!

echo -e "${C_CYAN}[*] 启动前端 vite dev (http://localhost:$FRONTEND_PORT) ...${C_RESET}"
(
    cd "$FRONTEND"
    PORT="$FRONTEND_PORT" npm run dev
) &
FRONTEND_PID=$!

echo ""
echo -e "${C_GREEN}==================================${C_RESET}"
echo -e "${C_GREEN} 服务已启动${C_RESET}"
echo -e "${C_GREEN}==================================${C_RESET}"
echo ""
echo -e "前端:    ${C_CYAN}http://localhost:$FRONTEND_PORT${C_RESET}"
echo -e "后端 API: ${C_CYAN}http://localhost:$BACKEND_PORT${C_RESET}"
echo -e "Swagger: ${C_CYAN}http://localhost:$BACKEND_PORT/docs${C_RESET}"
echo ""
echo -e "${C_YELLOW}按 Ctrl+C 停止所有服务。${C_RESET}"
echo ""

wait
