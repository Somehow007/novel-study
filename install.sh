#!/usr/bin/env bash
#
# Novel Study CLI 安装脚本（macOS / Linux）
# Windows 用户请使用 install.ps1
#
set -e

REPO="Somehow007/novel-study"
BIN_NAME="ns"
INSTALL_DIR="$HOME/.novel-study"
BIN_DIR="$HOME/.local/bin"

# ── 输出函数 ─────────────────────────────────────────────────────

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
    macos-arm64)  FILENAME="ns-macos-arm64.tar.gz" ;;
    macos-x64)    FILENAME="ns-macos-x64.tar.gz" ;;
    linux-x64)    FILENAME="ns-linux-x64.tar.gz" ;;
    linux-arm64)  FILENAME="ns-linux-arm64.tar.gz" ;;
    windows-*)    FILENAME="ns-windows.zip" ;;
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
TMP_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t ns)
trap "rm -rf '$TMP_DIR'" EXIT

if command -v curl &>/dev/null; then
    curl -fsSL "$DOWNLOAD_URL" -o "$TMP_DIR/$FILENAME"
elif command -v wget &>/dev/null; then
    wget -q "$DOWNLOAD_URL" -O "$TMP_DIR/$FILENAME"
else
    fail "需要 curl 或 wget"
fi

if [ ! -s "$TMP_DIR/$FILENAME" ]; then
    fail "下载失败，请检查网络或手动下载:"
    echo "  https://github.com/$REPO/releases"
fi
ok "下载完成"

# 5. 解压到安装目录
step "安装到 $INSTALL_DIR"

# 清理旧版本
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

cd "$TMP_DIR"
if [[ "$FILENAME" == *.tar.gz ]]; then
    tar xzf "$FILENAME"
elif [[ "$FILENAME" == *.zip ]]; then
    unzip -q "$FILENAME"
fi

if [ ! -f "$TMP_DIR/ns/$BIN_NAME" ]; then
    fail "解压后未找到 ns 可执行文件"
fi

# 移动整个目录（包含 _internal 依赖）
mv "$TMP_DIR/ns" "$INSTALL_DIR/ns"
chmod +x "$INSTALL_DIR/ns/$BIN_NAME"
ok "$INSTALL_DIR/ns/$BIN_NAME"

# 6. 创建 wrapper 到 PATH 目录
step "配置命令"
mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/$BIN_NAME" << EOF
#!/usr/bin/env bash
exec "$INSTALL_DIR/ns/$BIN_NAME" "\$@"
EOF
chmod +x "$BIN_DIR/$BIN_NAME"
ok "$BIN_DIR/$BIN_NAME → $INSTALL_DIR/ns/$BIN_NAME"

# 7. PATH 检查
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

# 8. 验证
step "验证安装"
if "$BIN_DIR/$BIN_NAME" --version >/dev/null 2>&1; then
    ok "$($BIN_DIR/$BIN_NAME --version)"
else
    warn "安装完成但验证失败，尝试运行 ns --help"
fi

# 9. 完成
echo ""
echo "┌─────────────────────────────────────┐"
echo "│   ✅ 安装完成！                      │"
echo "└─────────────────────────────────────┘"
echo ""
echo "  ns --help        查看所有命令"
echo "  ns --version     查看版本"
echo "  ns config init   交互式配置"
echo ""
