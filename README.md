<div align="center">

# 📚 Novel Study

**中文小说英语词汇自动注释工具**

在阅读中文小说的同时，自然积累英语词汇 —— 系统自动为小说中的高频词汇插入英文注释。

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](#-免责声明)

</div>

---

## ✨ 功能特性

- 📖 **智能注释** — 为中文小说自动内联插入英文注释（`原文(English [词性] 释义)`）
- 🕸️ **小说爬取** — 输入目录页 URL，自动爬取全本，支持断点续传、代理、并发控制
- 🧠 **多词库** — 内置 CET-4 / CET-6 / 考研词库，可自由组合
- ⚡ **高性能** — 50MB 整本小说 60 秒内处理完成（并行分词 + 二分密度过滤）
- 🛡️ **反爬检测** — 自动识别 Cloudflare / 验证码 / 登录墙 / VIP 付费等保护机制
- 🎚️ **密度控制** — 可调每句标注上限、字符窗口、最低难度分，避免注释过密
- 📦 **开箱即用** — 一行命令安装，无需 Python 环境，macOS / Linux 直接可用

## 📦 安装

### 一键安装（推荐）

**macOS / Linux：**

```bash
curl -fsSL https://raw.githubusercontent.com/Somehow007/novel-study/main/install.sh | bash
```

**Windows（PowerShell）：**

```powershell
irm https://raw.githubusercontent.com/Somehow007/novel-study/main/install.ps1 | iex
```

自动识别系统，下载对应可执行文件，配置环境变量。安装完成后直接使用 `ns` 命令。

### 手动下载

从 [GitHub Releases](https://github.com/Somehow007/novel-study/releases) 下载对应平台的可执行文件：

| 平台 | 文件 |
|------|------|
| macOS (Apple Silicon) | `ns-macos-arm64` |
| macOS (Intel) | `ns-macos-x64` |
| Linux (x64) | `ns-linux-x64` |
| Windows | `ns-windows.exe` |

```bash
# 示例：macOS Apple Silicon
curl -LO https://github.com/Somehow007/novel-study/releases/latest/download/ns-macos-arm64
chmod +x ns-macos-arm64
sudo mv ns-macos-arm64 /usr/local/bin/ns
```

### 从源码运行

```bash
git clone https://github.com/Somehow007/novel-study.git
cd novel-study
curl -LsSf https://astral.sh/uv/install.sh | sh  # 安装 uv
uv sync                                            # 安装依赖
uv run python cli.py --help                        # 使用 CLI
uv run uvicorn app:app --port 8000                 # 或启动 Web 界面
```

---

## 🚀 CLI 命令 (`ns`) 使用指南

### 爬取小说

```bash
# 基本用法 — 爬取全本，输出到当前目录
ns fetch https://www.example.com/book/12345/

# 指定章节范围
ns fetch <URL> --start 10 --end 50

# 多线程 + 断点续传
ns fetch <URL> --threads 5 --resume

# 使用代理（目标站点有反爬时）
ns fetch <URL> --proxy http://127.0.0.1:7890

# 调整请求间隔（秒）和批量写入频率
ns fetch <URL> --delay 1 --batch 100

# 指定输出目录
ns fetch <URL> -o ~/novels/

# 强制编码
ns fetch <URL> --encoding gbk
```

### 注释文本

```bash
# 基本用法 — 默认使用全部词库，输出到当前目录
ns annotate novel.txt

# 指定词库
ns annotate novel.txt --vocab cet6,kaoyan

# 调整密度参数
ns annotate novel.txt --min-score 2.0 --max-sentence 2 --max-chars 80

# 指定输出文件名和目录
ns annotate novel.txt -o annotated.txt --output-dir ~/output/

# 大文件强制并行
ns annotate novel.txt --parallel

# 静默模式（不输出预览）
ns annotate novel.txt -q
```

### 词库管理

```bash
# 查看所有可用词库
ns vocab list

# 查看某个词库详情
ns vocab info cet6
```

### 配置管理

配置文件位于 `~/.novel-study/config.json`，所有命令的默认参数都从这里读取。

```bash
# 交互式配置向导（首次推荐）
ns config init

# 查看当前配置
ns config show

# 获取单个配置值
ns config get default_threads

# 修改配置
ns config set default_threads 8
ns config set default_delay 1
ns config set default_vocab cet6,kaoyan
ns config set proxy http://127.0.0.1:7890
ns config set output_dir ~/novels

# 用编辑器打开配置文件
ns config edit

# 重置为默认值
ns config reset
```

**可配置项：**

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `default_threads` | 默认爬取线程数 | 3 |
| `default_delay` | 默认请求间隔（秒） | 0.5 |
| `default_batch` | 多少章写入一次文件 | 50 |
| `default_vocab` | 默认词库列表 | cet4,cet6,kaoyan |
| `default_min_score` | 最低难度分数 | 1.5 |
| `default_max_per_sentence` | 每句最多标注词数 | 3 |
| `default_max_per_chars` | 字符窗口大小 | 100 |
| `proxy` | HTTP 代理地址 | null |
| `output_dir` | 默认输出目录 | null（当前目录） |

### Web 服务

```bash
# 启动 Web 界面（从源码运行时可用）
ns serve --port 8000
```

浏览器打开 `http://localhost:8000`，支持拖拽上传、实时进度、可视化参数调节。

### 自更新

```bash
# 从源码运行时，拉取最新代码并更新依赖
ns update
```

打包版不支持自动更新，请重新下载最新版本。

---

## 🌐 Web 界面

从源码运行 `ns serve` 启动后，浏览器有两个功能标签：

| 标签 | 功能 | 说明 |
|------|------|------|
| 🕸️ **爬取小说** | 输入小说目录页 URL | 自动检测章节、并发下载、实时进度 |
| 📖 **文本处理** | 上传 `.txt` 文件 | 选词库、调参数、实时进度、高亮预览 |

## 🔌 API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/annotate` | POST | 上传文件注释 |
| `/api/fetch/stream` | GET | 爬取小说（SSE 实时进度） |
| `/api/vocabs` | GET | 获取可用词库列表 |
| `/api/system/info` | GET | 系统信息（最大线程数等） |
| `/api/download` | GET | 下载爬取结果文件 |
| `/api/health` | GET | 健康检查 |

## 📁 项目结构

```
novel-study/
├── cli.py                 # CLI 入口（ns 命令）
├── config.py              # 配置管理模块
├── ns.spec                # PyInstaller 打包配置
├── install.sh             # 一键安装脚本
├── app.py                 # FastAPI Web API
├── main.py                # 核心处理引擎（process_text）
├── core/                  # 分词、匹配、注释、密度控制
├── vocab/                 # 词库数据 + 加载器
├── scripts/
│   └── fetch_novel.py     # 小说爬取核心逻辑
├── static/index.html      # Web 前端
├── data/                  # 爬取的小说
└── output/                # 注释结果
```

## 🧪 运行测试

```bash
uv run pytest
```

## ⚠️ 免责声明

> **本工具仅供学习交流和个人研究使用。**

1. **版权尊重** — 爬取功能仅用于获取可公开访问的网页内容。用户应遵守目标网站的使用条款。
2. **合理使用** — 请勿对目标站点发起高频请求或大规模爬取。
3. **内容免责** — 本工具不对爬取内容的合法性、准确性负责。
4. **反爬绕过** — Cloudflare 绕过仅用于访问公开可读内容，不用于规避付费墙。
5. **禁止商用** — 请勿将本工具用于任何商业用途或侵犯他人权益的行为。

**使用本工具即表示您已阅读并同意上述声明。**

## 📄 License

[MIT](LICENSE)
