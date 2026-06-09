# Novel Study CLI — Windows 安装脚本
#
# 用法（PowerShell）：
#   irm https://raw.githubusercontent.com/Somehow007/novel-study/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

$REPO = "Somehow007/novel-study"
$BIN_NAME = "ns.exe"
$INSTALL_DIR = "$env:USERPROFILE\.novel-study"
$BIN_DIR = "$env:USERPROFILE\.local\bin"

Write-Host ""
Write-Host "+-------------------------------------+" -ForegroundColor Cyan
Write-Host "|   Novel Study CLI 安装程序          |" -ForegroundColor Cyan
Write-Host "+-------------------------------------+" -ForegroundColor Cyan

# 1. 检测系统
Write-Host ""
Write-Host "-> 检测系统平台" -ForegroundColor Yellow
$ARCH = if ([Environment]::Is64BitOperatingSystem) { "x64" } else { "x86" }
Write-Host "  [OK] windows-$ARCH" -ForegroundColor Green

# 2. 获取最新版本
Write-Host ""
Write-Host "-> 获取最新版本" -ForegroundColor Yellow
try {
    $RELEASE = Invoke-RestMethod -Uri "https://api.github.com/repos/$REPO/releases/latest"
    $VERSION = $RELEASE.tag_name
    Write-Host "  [OK] $VERSION" -ForegroundColor Green
} catch {
    Write-Host "  [!] 无法获取版本号，使用 latest" -ForegroundColor Yellow
    $VERSION = $null
}

$FILENAME = "ns-windows-x64.zip"
if ($VERSION) {
    $DOWNLOAD_URL = "https://github.com/$REPO/releases/download/$VERSION/$FILENAME"
} else {
    $DOWNLOAD_URL = "https://github.com/$REPO/releases/latest/download/$FILENAME"
}

# 3. 下载
Write-Host ""
Write-Host "-> 下载 $FILENAME" -ForegroundColor Yellow
$TMP_DIR = Join-Path $env:TEMP "ns-install-$(Get-Random)"
New-Item -ItemType Directory -Path $TMP_DIR -Force | Out-Null

try {
    Invoke-WebRequest -Uri $DOWNLOAD_URL -OutFile "$TMP_DIR\$FILENAME" -UseBasicParsing
    Write-Host "  [OK] 下载完成" -ForegroundColor Green
} catch {
    Write-Host "  [X] 下载失败: $_" -ForegroundColor Red
    Write-Host "  手动下载: https://github.com/$REPO/releases" -ForegroundColor Yellow
    exit 1
}

# 4. 解压安装
Write-Host ""
Write-Host "-> 安装到 $INSTALL_DIR" -ForegroundColor Yellow

if (Test-Path $INSTALL_DIR) {
    Remove-Item -Recurse -Force $INSTALL_DIR
}
New-Item -ItemType Directory -Path $INSTALL_DIR -Force | Out-Null

Expand-Archive -Path "$TMP_DIR\$FILENAME" -DestinationPath $TMP_DIR -Force

# 解压后目录结构: $TMP_DIR\ns\ns.exe + _internal\
$EXTRACTED = "$TMP_DIR\ns"
if (-not (Test-Path "$EXTRACTED\$BIN_NAME")) {
    Write-Host "  [X] 解压后未找到 ns.exe" -ForegroundColor Red
    exit 1
}

Move-Item -Path $EXTRACTED -Destination "$INSTALL_DIR\ns"
Write-Host "  [OK] $INSTALL_DIR\ns\$BIN_NAME" -ForegroundColor Green

# 5. 创建 wrapper 到 PATH 目录
Write-Host ""
Write-Host "-> 配置命令" -ForegroundColor Yellow

New-Item -ItemType Directory -Path $BIN_DIR -Force | Out-Null

$WRAPPER = @"
@echo off
"$INSTALL_DIR\ns\$BIN_NAME" %*
"@
Set-Content -Path "$BIN_DIR\ns.cmd" -Value $WRAPPER -Encoding ASCII
Write-Host "  [OK] $BIN_DIR\ns.cmd" -ForegroundColor Green

# 6. PATH 检查
Write-Host ""
Write-Host "-> 检查环境变量" -ForegroundColor Yellow

$CURRENT_PATH = [Environment]::GetEnvironmentVariable("Path", "User")
if ($CURRENT_PATH -like "*$BIN_DIR*") {
    Write-Host "  [OK] ~/.local/bin 已在 PATH 中" -ForegroundColor Green
} else {
    Write-Host "  [!] 正在添加到 PATH..." -ForegroundColor Yellow
    $NEW_PATH = "$BIN_DIR;$CURRENT_PATH"
    [Environment]::SetEnvironmentVariable("Path", $NEW_PATH, "User")
    $env:Path = "$BIN_DIR;$env:Path"
    Write-Host "  [OK] 已添加到用户 PATH" -ForegroundColor Green
    Write-Host ""
    Write-Host "  新开的 PowerShell 窗口会自动生效" -ForegroundColor Yellow
}

# 7. 验证
Write-Host ""
Write-Host "-> 验证安装" -ForegroundColor Yellow
try {
    $VER = & "$BIN_DIR\ns.cmd" --version 2>&1
    Write-Host "  [OK] $VER" -ForegroundColor Green
} catch {
    Write-Host "  [!] 安装完成但验证失败，请运行 ns --help" -ForegroundColor Yellow
}

# 8. 清理
Remove-Item -Recurse -Force $TMP_DIR -ErrorAction SilentlyContinue

# 9. 完成
Write-Host ""
Write-Host "+-------------------------------------+" -ForegroundColor Cyan
Write-Host "|   [OK] 安装完成！                    |" -ForegroundColor Cyan
Write-Host "+-------------------------------------+" -ForegroundColor Cyan
Write-Host ""
Write-Host "  ns --help        查看所有命令"
Write-Host "  ns --version     查看版本"
Write-Host "  ns config init   交互式配置"
Write-Host ""
