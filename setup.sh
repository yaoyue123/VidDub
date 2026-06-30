#!/usr/bin/env bash
# setup.sh — VidDub 一键初始化脚本 (uv 版)
#
# 用法: chmod +x setup.sh && ./setup.sh
#
# 自动完成:
#   1. 检查/安装 uv (Python 包管理器)
#   2. uv sync 创建 .venv + 安装后端依赖
#   3. 安装 Playwright Chromium
#   4. 安装前端 npm 依赖
#   5. 复制 .env.example → .env（如不存在）
#   6. 执行数据库迁移

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$PROJECT_ROOT/backend"
FRONTEND="$PROJECT_ROOT/frontend"

C_CYAN="\033[36m"
C_GREEN="\033[32m"
C_YELLOW="\033[33m"
C_RED="\033[31m"
C_RESET="\033[0m"

log()  { echo -e "${C_CYAN}[*]${C_RESET} $1"; }
ok()   { echo -e "${C_GREEN}[✓]${C_RESET} $1"; }
warn() { echo -e "${C_YELLOW}[!]${C_RESET} $1"; }
fail() { echo -e "${C_RED}[FAIL]${C_RESET} $1"; exit 1; }

echo "=================================="
echo " VidDub 环境初始化"
echo "=================================="

# ── 1. 检查 uv ──
if ! command -v uv &>/dev/null; then
    log "未找到 uv，正在安装..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # 重新加载 PATH
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
    command -v uv &>/dev/null || fail "uv 安装失败。请手动安装: https://docs.astral.sh/uv/"
    ok "uv 已安装"
else
    ok "uv 已就绪 ($(command -v uv))"
fi

# ── 2. 安装后端依赖 ──
log "安装后端依赖..."
cd "$BACKEND"
uv sync --group dev
ok "后端依赖已安装"

# ── 3. 安装 Playwright Chromium ──
log "检查 Playwright Chromium..."
PLAYWRIGHT_DIR="$HOME/.cache/ms-playwright"
if [ ! -d "$PLAYWRIGHT_DIR" ] || [ -z "$(ls -A "$PLAYWRIGHT_DIR" 2>/dev/null)" ]; then
    log "安装 Playwright Chromium..."
    uv run python -m playwright install chromium
    ok "Playwright Chromium 已安装"
else
    ok "Playwright Chromium 已就绪"
fi

# ── 4. 安装前端依赖 ──
log "安装前端依赖..."
cd "$FRONTEND"
npm install
ok "前端依赖已安装"

# ── 5. 复制 .env ──
if [ ! -f "$BACKEND/.env" ]; then
    if [ -f "$BACKEND/.env.example" ]; then
        cp "$BACKEND/.env.example" "$BACKEND/.env"
        ok "已创建 backend/.env（请编辑填入 SILICONFLOW_API_KEY）"
    fi
else
    ok "backend/.env 已存在"
fi

# ── 6. 数据库迁移 ──
log "执行数据库迁移..."
cd "$BACKEND"
uv run alembic upgrade head
ok "数据库迁移完成"

cd "$PROJECT_ROOT"
echo ""
echo -e "${C_GREEN}==================================${C_RESET}"
echo -e "${C_GREEN}  VidDub 初始化完成！${C_RESET}"
echo -e "${C_GREEN}==================================${C_RESET}"
echo ""
echo -e "启动: ${C_CYAN}./start.sh${C_RESET}"
echo ""
