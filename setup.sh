#!/usr/bin/env bash
# You2Bili 一键环境初始化脚本 (Linux / macOS)
#
# 用法:
#   ./setup.sh [--whisper-model tiny|base|small|medium] [--skip-frontend] [--skip-playwright]
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$PROJECT_ROOT/backend"
FRONTEND="$PROJECT_ROOT/frontend"

WHISPER_MODEL="tiny"
SKIP_FRONTEND=0
SKIP_PLAYWRIGHT=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --whisper-model)
            WHISPER_MODEL="$2"; shift 2 ;;
        --skip-frontend)
            SKIP_FRONTEND=1; shift ;;
        --skip-playwright)
            SKIP_PLAYWRIGHT=1; shift ;;
        -h|--help)
            sed -n '2,10p' "$0"; exit 0 ;;
        *)
            echo "[!] 未知参数: $1" >&2; exit 2 ;;
    esac
done

C_RESET="\033[0m"; C_CYAN="\033[36m"; C_GREEN="\033[32m"; C_YELLOW="\033[33m"; C_RED="\033[31m"
step() { echo -e "\n${C_CYAN}[*] $1${C_RESET}"; }
ok()   { echo -e "${C_GREEN}[OK] $1${C_RESET}"; }
warn() { echo -e "${C_YELLOW}[!] $1${C_RESET}"; }
die()  { echo -e "${C_RED}[FAIL] $1${C_RESET}"; exit 1; }

echo "=================================="
echo " You2Bili Setup (Linux/macOS)"
echo "=================================="

# ─────────────────────────────────────────────────────────
# 1. 依赖检查
# ─────────────────────────────────────────────────────────
step "检查系统依赖..."

command -v python3 >/dev/null 2>&1 || die "未找到 python3，请安装 Python 3.10+"
PY_VER="$(python3 -c 'import sys;print("%d.%d" % sys.version_info[:2])')"
PY_MAJOR="${PY_VER%%.*}"; PY_MINOR="${PY_VER##*.}"
if [[ "$PY_MAJOR" -lt 3 || ($PY_MAJOR -eq 3 && "$PY_MINOR" -lt 10) ]]; then
    die "Python 版本过低: $PY_VER (需要 3.10+)"
fi
ok "Python: $(python3 --version)"

command -v node >/dev/null 2>&1 || die "未找到 node，请安装 Node.js 18+"
NODE_MAJOR="$(node --version | sed 's/v\([0-9]*\)\..*/\1/')"
if [[ "$NODE_MAJOR" -lt 18 ]]; then die "Node 版本过低 (需要 18+)"; fi
ok "Node: $(node --version)"

command -v npm >/dev/null 2>&1 || die "未找到 npm"
ok "npm: $(npm --version)"

command -v ffmpeg >/dev/null 2>&1 || die "未找到 ffmpeg (apt: sudo apt install ffmpeg / brew: brew install ffmpeg)"
ok "ffmpeg: $(ffmpeg -version | head -1)"

if command -v yt-dlp >/dev/null 2>&1; then ok "yt-dlp: $(yt-dlp --version | head -1)"; else
    warn "yt-dlp 未在 PATH (将在 pip install 时一并安装)"
fi

# ─────────────────────────────────────────────────────────
# 2. venv + pip
# ─────────────────────────────────────────────────────────
step "创建 Python 虚拟环境 backend/venv/ ..."
VENV_PY="$BACKEND/venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
    (cd "$BACKEND" && python3 -m venv venv) || die "创建 venv 失败"
    ok "venv 创建完成"
else
    ok "venv 已存在，跳过创建"
fi

step "安装 Python 依赖 (requirements.txt) ..."
"$VENV_PY" -m pip install --upgrade pip wheel >/dev/null
"$VENV_PY" -m pip install -r "$BACKEND/requirements.txt" || die "pip install 失败"
ok "Python 依赖安装完成"

# ─────────────────────────────────────────────────────────
# 3. Playwright Chromium
# ─────────────────────────────────────────────────────────
if [[ "$SKIP_PLAYwright" -eq 0 ]]; then
    step "安装 Playwright Chromium ..."
    if "$VENV_PY" -m playwright install chromium; then
        ok "Playwright Chromium 安装完成"
    else
        warn "playwright install chromium 失败 — 平台登录/发布将不可用，其它功能不受影响"
    fi
else
    warn "已跳过 Playwright 安装"
fi

# ─────────────────────────────────────────────────────────
# 4. Frontend npm install
# ─────────────────────────────────────────────────────────
if [[ "$SKIP_FRONTEND" -eq 0 ]]; then
    step "安装前端 npm 依赖 ..."
    (cd "$FRONTEND" && npm install) || die "npm install 失败"
    ok "前端依赖安装完成"
else
    warn "已跳过前端依赖安装"
fi

# ─────────────────────────────────────────────────────────
# 5. 预下载 Whisper 模型
# ─────────────────────────────────────────────────────────
step "预下载 Whisper 模型 ($WHISPER_MODEL) ..."
if "$VENV_PY" -c "import whisper; m = whisper.load_model('$WHISPER_MODEL'); print('loaded:', m.device)"; then
    ok "Whisper 模型 $WHISPER_MODEL 已就绪"
else
    warn "Whisper 预下载失败 — 首次运行时会重试，建议检查网络/镜像源"
fi

# ─────────────────────────────────────────────────────────
# 6. 数据库迁移
# ─────────────────────────────────────────────────────────
step "运行 Alembic 数据库迁移 ..."
if (cd "$BACKEND" && "$VENV_PY" -m alembic upgrade head); then
    ok "数据库迁移完成"
else
    warn "Alembic 迁移失败 — 请检查 backend/alembic/versions/ 与 backend/data/you2bili.db 权限"
fi

# ─────────────────────────────────────────────────────────
# 7. .env 检查
# ─────────────────────────────────────────────────────────
ENV_FILE="$BACKEND/.env"
ENV_EXAMPLE="$BACKEND/.env.example"
if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "$ENV_EXAMPLE" ]]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        warn "已从 .env.example 复制创建 backend/.env — 必须填入 SILICONFLOW_API_KEY"
    else
        warn "未找到 backend/.env — 配音功能将无法启动"
    fi
else
    ok "backend/.env 已存在"
fi

# ─────────────────────────────────────────────────────────
# 8. 完成提示
# ─────────────────────────────────────────────────────────
echo ""
echo "=================================="
echo -e "${C_GREEN} Setup 完成！${C_RESET}"
echo "=================================="
echo ""
echo -e "${C_CYAN}下一步：${C_RESET}"
echo "  1. 编辑 backend/.env，填入 SILICONFLOW_API_KEY"
echo "     申请地址: https://cloud.siliconflow.cn/account/ak"
echo "  2. 启动服务："
echo "       $ ./start.sh"
echo "  3. 访问前端: http://localhost:5173"
echo "  4. FastAPI 文档: http://localhost:8000/docs"
echo ""
echo -e "${C_CYAN}更多文档：${C_RESET}"
echo "  - README.md"
echo "  - docs/CONFIGURATION.md"
echo "  - docs/TROUBLESHOOTING.md"
echo "  - docs/ARCHITECTURE.md"
echo ""
