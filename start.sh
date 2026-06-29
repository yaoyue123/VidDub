#!/usr/bin/env bash
# VidDub 一键启动脚本 (Linux / macOS)
#
# 用法: ./start.sh [backend_port] [frontend_port]
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$PROJECT_ROOT/backend"
FRONTEND="$PROJECT_ROOT/frontend"

BACKEND_PORT="${1:-8000}"
FRONTEND_PORT="${2:-5173}"

VENV_PY="$BACKEND/venv/bin/python"
VENV_UVICORN="$BACKEND/venv/bin/uvicorn"

C_CYAN="\033[36m"; C_GREEN="\033[32m"; C_YELLOW="\033[33m"; C_RED="\033[31m"; C_RESET="\033[0m"

echo "=================================="
echo " VidDub 启动 (Linux/macOS)"
echo "=================================="

[[ -x "$VENV_PY" ]] || { echo -e "${C_RED}[FAIL] 未找到 backend/venv，请先运行 ./setup.sh${C_RESET}"; exit 1; }
[[ -d "$FRONTEND/node_modules" ]] || { echo -e "${C_RED}[FAIL] 未找到 frontend/node_modules，请先运行 ./setup.sh${C_RESET}"; exit 1; }
[[ -f "$BACKEND/.env" ]] || echo -e "${C_YELLOW}[!] 未找到 backend/.env — 配音功能需要 SILICONFLOW_API_KEY${C_RESET}"

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
    "$VENV_UVICORN" app.main:app \
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
