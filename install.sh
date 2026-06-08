#!/usr/bin/env bash
set -e

REPO_URL="https://github.com/Somehow007/novel-study.git"
INSTALL_DIR="$HOME/.novel-study"
BIN_DIR="$HOME/.local/bin"
NS_BIN="$BIN_DIR/ns"

# ── 颜色 ────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
info() { echo -e "${BOLD}$*${NC}"; }
warn() { echo -e "${YELLOW}[提示]${NC} $*"; }
err()  { echo -e "${RED}[错误]${NC} $*"; exit 1; }

# ── 环境检查 ─────────────────────────────────────────────────────

info "📦 Novel Study 安装脚本"
echo ""

# Python 版本检查
if ! command -v python3 &>/dev/null; then
    err "未找到 python3，请先安装 Python 3.12+"
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]); then
    err "Python 版本过低（当前 $PY_VERSION），需要 3.12+"
fi
ok "Python $PY_VERSION"

# git 检查
if ! command -v git &>/dev/null; then
    err "未找到 git，请先安装 git"
fi
ok "git $(git --version | awk '{print $3}')"

# ── 克隆/更新仓库 ────────────────────────────────────────────────

if [ -d "$INSTALL_DIR/.git" ]; then
    info "🔄 更新已有安装..."
    cd "$INSTALL_DIR"
    git pull --ff-only 2>/dev/null || warn "git pull 失败，使用现有版本"
    ok "仓库已更新"
else
    info "📥 下载项目..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    ok "已克隆到 $INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── 安装依赖 ─────────────────────────────────────────────────────

info "📦 安装依赖..."

if command -v uv &>/dev/null; then
    ok "使用 uv 安装"
    uv sync --quiet 2>/dev/null || uv sync
else
    warn "未找到 uv，使用 pip 安装（建议安装 uv 以获得更好体验）"
    python3 -m pip install -e . --quiet --break-system-packages 2>/dev/null \
        || python3 -m pip install -e . --quiet
fi

ok "依赖安装完成"

# ── 创建 ns 命令 ─────────────────────────────────────────────────

info "🔗 创建 ns 命令..."

mkdir -p "$BIN_DIR"

cat > "$NS_BIN" << 'WRAPPER'
#!/usr/bin/env bash
# ns — Novel Study CLI wrapper
INSTALL_DIR="$HOME/.novel-study"

if command -v uv &>/dev/null; then
    cd "$INSTALL_DIR" && exec uv run python cli.py "$@"
else
    cd "$INSTALL_DIR" && exec python3 cli.py "$@"
fi
WRAPPER

chmod +x "$NS_BIN"
ok "已创建 $NS_BIN"

# ── PATH 检查 ────────────────────────────────────────────────────

case ":$PATH:" in
    *":$BIN_DIR:"*)
        ok "~/.local/bin 已在 PATH 中"
        ;;
    *)
        warn "~/.local/bin 不在 PATH 中，正在添加..."

        # 检测 shell 配置文件
        SHELL_NAME=$(basename "$SHELL")
        case "$SHELL_NAME" in
            zsh)  RC_FILE="$HOME/.zshrc" ;;
            bash) RC_FILE="$HOME/.bashrc" ;;
            *)    RC_FILE="$HOME/.profile" ;;
        esac

        # 添加到 PATH
        echo '' >> "$RC_FILE"
        echo '# Novel Study CLI' >> "$RC_FILE"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC_FILE"

        warn "已添加到 $RC_FILE，请运行以下命令使其生效："
        echo ""
        echo -e "  ${BOLD}source $RC_FILE${NC}"
        echo ""
        ;;
esac

# ── 完成 ─────────────────────────────────────────────────────────

echo ""
info "✅ 安装完成！"
echo ""
echo -e "  运行 ${BOLD}ns --help${NC} 查看使用说明"
echo -e "  运行 ${BOLD}ns config show${NC} 查看默认配置"
echo -e "  运行 ${BOLD}ns update${NC} 更新到最新版本"
echo ""
