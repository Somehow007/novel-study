#!/usr/bin/env bash
set -e

REPO="Somehow007/novel-study"
BIN_NAME="ns"
BIN_DIR="$HOME/.local/bin"

# ── 输出函数（简洁、干净）────────────────────────────────────────

step()  { printf "\n→ %s\n" "$*"; }
ok()    { printf "  ✓ %s\n" "$*"; }
warn()  { printf "  ⚠ %s\n" "$*"; }
fail()  { printf "  ✗ %s\n" "$*"; exit 1; }

# ── 检测系统和架构 ──────────────────────────────────────────────

detect_platform() {
    local os arch
    case "$(uname -s)" in
        Darwin*)  os="macos" ;;
        Linux*)   os="linux" ;;
        MINGW*|MSYS*|CYGWIN*) os="windows" ;;
        *) fail "不支持的操作系统: $(uname -s)" ;;
    esac
    case "$(uname -m)" in
        x86_64|amd64)  arch="x64" ;;
        aarch64|arm64) arch="arm64" ;;
        *) fail "不支持的架构: $(uname -m)" ;;
    esac
    echo "${os}-${arch}"
}

# ── 主流程 ──────────────────────────────────────────────────────

echo ""
echo "┌─────────────────────────────────────┐"
echo "│   Novel Study CLI 安装程序          │"
echo "└─────────────────────────────────────┘"

# 1. 检测平台
step "检测系统平台"
PLATFORM=$(detect_platform)
ok "$PLATFORM"

# 2. 确定下载文件
case "$PLATFORM" in
    macos-arm64)  FILENAME="ns-macos-arm64" ;;
    macos-x64)    FILENAME="ns-macos-x64" ;;
    linux-x64)    FILENAME="ns-linux-x64" ;;
    linux-arm64)  FILENAME="ns-linux-arm64" ;;
    windows-*)    FILENAME="ns-windows.exe" ;;
esac

# 3. 获取最新版本
step "获取最新版本"
LATEST=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null \
    | grep '"tag_name"' | head -1 | sed -E 's/.*"([^"]+)".*/\1/')

if [ -n "$LATEST" ]; then
    ok "$LATEST"
    DOWNLOAD_URL="https://github.com/$REPO/releases/download/$LATEST/$FILENAME"
else
    warn "无法获取版本号，使用 latest"
    DOWNLOAD_URL="https://github.com/$REPO/releases/latest/download/$FILENAME"
fi

# 4. 下载
step "下载 $FILENAME"
TMP_FILE=$(mktemp 2>/dev/null || mktemp -t ns)
trap "rm -f '$TMP_FILE'" EXIT

if command -v curl &>/dev/null; then
    curl -fsSL "$DOWNLOAD_URL" -o "$TMP_FILE"
elif command -v wget &>/dev/null; then
    wget -q "$DOWNLOAD_URL" -O "$TMP_FILE"
else
    fail "需要 curl 或 wget"
fi

if [ ! -s "$TMP_FILE" ]; then
    fail "下载失败，请检查网络或手动下载:"
    echo "  https://github.com/$REPO/releases"
fi
ok "下载完成"

# 5. 安装
step "安装到 $BIN_DIR"
mkdir -p "$BIN_DIR"
DEST="$BIN_DIR/$BIN_NAME"
mv "$TMP_FILE" "$DEST"
chmod +x "$DEST"
ok "$DEST"

# 6. PATH 检查
step "检查环境变量"
case ":$PATH:" in
    *":$BIN_DIR:"*)
        ok "~/.local/bin 已在 PATH 中"
        ;;
    *)
        warn "~/.local/bin 不在 PATH 中，正在添加..."
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
        ok "已写入 $RC_FILE"
        echo ""
        echo "  请运行以下命令使 PATH 生效："
        echo "    source $RC_FILE"
        ;;
esac

# 7. 完成
echo ""
echo "┌─────────────────────────────────────┐"
echo "│   ✅ 安装完成！                      │"
echo "└─────────────────────────────────────┘"
echo ""
echo "  ns --help        查看所有命令"
echo "  ns --version     查看版本"
echo "  ns config init   交互式配置"
echo ""
