#!/usr/bin/env bash
set -e

# ── Novel Study CLI 一键安装脚本 ─────────────────────────────────
#
# 用法：
#   curl -sSL https://raw.githubusercontent.com/Somehow007/novel-study/main/install.sh | bash
#
# 自动识别系统和架构，下载对应可执行文件，放到 PATH 中。

REPO="Somehow007/novel-study"
BIN_NAME="ns"
BIN_DIR="$HOME/.local/bin"

# ── 颜色 ────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $*"; }
info() { echo -e "${BOLD}$*${NC}"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; exit 1; }

# ── 检测系统和架构 ──────────────────────────────────────────────

detect_platform() {
    local os arch

    case "$(uname -s)" in
        Darwin*)  os="macos" ;;
        Linux*)   os="linux" ;;
        MINGW*|MSYS*|CYGWIN*) os="windows" ;;
        *) err "不支持的操作系统: $(uname -s)" ;;
    esac

    case "$(uname -m)" in
        x86_64|amd64)  arch="x64" ;;
        aarch64|arm64) arch="arm64" ;;
        *) err "不支持的架构: $(uname -m)" ;;
    esac

    echo "${os}-${arch}"
}

# ── 下载工具（优先 curl，回退 wget）─────────────────────────────

download() {
    local url="$1" output="$2"
    if command -v curl &>/dev/null; then
        curl -fSL --progress-bar "$url" -o "$output"
    elif command -v wget &>/dev/null; then
        wget -q --show-progress "$url" -O "$output"
    else
        err "需要 curl 或 wget，请先安装其中一个"
    fi
}

# ── 主流程 ──────────────────────────────────────────────────────

info "📦 Novel Study CLI 安装脚本"
echo ""

# 1. 检测平台
PLATFORM=$(detect_platform)
ok "检测到平台: $PLATFORM"

# 2. 确定下载文件名
case "$PLATFORM" in
    macos-arm64)  FILENAME="ns-macos-arm64" ;;
    macos-x64)    FILENAME="ns-macos-x64" ;;
    linux-x64)    FILENAME="ns-linux-x64" ;;
    linux-arm64)  FILENAME="ns-linux-arm64" ;;
    windows-*)    FILENAME="ns-windows.exe" ;;
esac

# 3. 获取最新版本号
info "获取最新版本..."
LATEST=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null \
    | grep '"tag_name"' | head -1 | sed -E 's/.*"([^"]+)".*/\1/')

if [ -z "$LATEST" ]; then
    warn "无法获取版本号，使用 main 分支"
    DOWNLOAD_URL="https://github.com/$REPO/releases/latest/download/$FILENAME"
else
    ok "最新版本: $LATEST"
    DOWNLOAD_URL="https://github.com/$REPO/releases/download/$LATEST/$FILENAME"
fi

# 4. 下载
TMP_FILE=$(mktemp 2>/dev/null || mktemp -t ns)
trap "rm -f '$TMP_FILE'" EXIT

info "下载 $FILENAME ..."
download "$DOWNLOAD_URL" "$TMP_FILE"

if [ ! -s "$TMP_FILE" ]; then
    err "下载失败，请检查网络或手动下载: https://github.com/$REPO/releases"
fi
ok "下载完成"

# 5. 安装
mkdir -p "$BIN_DIR"

DEST="$BIN_DIR/$BIN_NAME"
[ "$PLATFORM" = "windows-"* ] && DEST="$DEST.exe"

mv "$TMP_FILE" "$DEST"
chmod +x "$DEST"
ok "已安装到 $DEST"

# 6. PATH 检查
case ":$PATH:" in
    *":$BIN_DIR:"*)
        ok "~/.local/bin 已在 PATH 中"
        ;;
    *)
        warn "~/.local/bin 不在 PATH 中，正在配置..."

        SHELL_NAME=$(basename "$SHELL")
        case "$SHELL_NAME" in
            zsh)  RC_FILE="$HOME/.zshrc" ;;
            bash) RC_FILE="$HOME/.bashrc" ;;
            fish) RC_FILE="$HOME/.config/fish/config.fish" ;;
            *)    RC_FILE="$HOME/.profile" ;;
        esac

        if [ "$SHELL_NAME" = "fish" ]; then
            echo "set -gx PATH $BIN_DIR \$PATH" >> "$RC_FILE"
        else
            echo '' >> "$RC_FILE"
            echo '# Novel Study CLI' >> "$RC_FILE"
            echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$RC_FILE"
        fi

        warn "已添加到 $RC_FILE"
        echo ""
        echo -e "  运行 ${BOLD}source $RC_FILE${NC} 或重新打开终端使其生效"
        ;;
esac

# 7. 完成
echo ""
info "✅ 安装完成！"
echo ""
echo -e "  ${BOLD}ns --help${NC}     查看所有命令"
echo -e "  ${BOLD}ns --version${NC}  查看版本"
echo -e "  ${BOLD}ns config init${NC} 交互式配置"
echo ""
