<div align="center">

# 📚 Novel Study

**中文小说英语词汇自动注释工具**

在阅读中文小说的同时，自然积累英语词汇 —— 系统自动为小说中的高频词汇插入英文注释。

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](#-免责声明)

</div>

---

## ✨ 功能特性

- 📖 **智能注释** — 上传中文小说 `.txt`，自动内联插入英文注释（`原文(English [词性] 释义)`）
- 🕸️ **小说爬取** — 输入小说目录页 URL，自动爬取全本内容，命令行支持断点续传（`--resume`）
- 📊 **实时进度** — Web 端 SSE 实时推送爬取/处理进度，不再干等
- 🧠 **多词库** — 内置 CET-4 / CET-6 / 考研词库，可自由组合
- ⚡ **高性能** — 50MB 整本小说 60 秒内处理完成（并行分词 + 二分密度过滤）
- 🛡️ **反爬检测** — 自动识别 Cloudflare / 验证码 / 登录墙 / VIP 付费等保护机制
- 🎚️ **密度控制** — 可调每句标注上限、字符窗口、最低难度分，避免注释过密

## 📦 快速开始

### 1. 安装 uv（一行命令）

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 克隆 & 安装依赖

```bash
git clone https://github.com/Somehow007/novel-study.git
cd novel-study
uv sync
```

> 首次运行会自动下载 jieba 词典和词库数据，无需手动操作。

### 3. 启动

```bash
# Web 界面（推荐）
uv run uvicorn app:app --host 0.0.0.0 --port 8000

# 命令行处理
uv run python main.py sample.txt

# 命令行爬取小说
uv run python scripts/fetch_novel.py https://www.example.com/book/12345/
```

打开浏览器访问 `http://localhost:8000` 即可使用 Web 界面。

## 🚀 使用指南

### Web 界面

启动后打开浏览器，有两个功能标签：

| 标签 | 功能 | 说明 |
|------|------|------|
| 🕸️ **爬取小说** | 输入小说目录页 URL | 自动检测章节、并发下载、实时进度 |
| 📖 **文本处理** | 上传 `.txt` 文件 | 选词库、调参数、实时进度、高亮预览 |

### 命令行 — 文本注释

```bash
# 基本用法（默认使用 CET-4/6 + 考研词库）
uv run python main.py sample.txt

# 指定参数
uv run python main.py sample.txt --max-sentence=5 --min-score=2.0

# 并行模式（大文件推荐）
uv run python main.py sample.txt --parallel
```

输出文件保存在 `output/` 目录。

### 命令行 — 爬取小说

```bash
# 基本用法
uv run python scripts/fetch_novel.py https://www.example.com/book/12345/

# 指定章节范围
uv run python scripts/fetch_novel.py <URL> --start 10 --end 50

# 断点续传
uv run python scripts/fetch_novel.py <URL> --resume

# 调整并发和延迟（线程数超过系统上限会自动调整）
uv run python scripts/fetch_novel.py <URL> --threads 5 --delay 1

# 使用代理
uv run python scripts/fetch_novel.py <URL> --proxy http://127.0.0.1:7890
```

输出文件保存在 `data/<书名>/` 目录。

### API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/annotate` | POST | 上传文件注释（同步） |
| `/api/annotate/stream` | POST | 上传文件注释（SSE 实时进度） |
| `/api/fetch/stream` | GET | 爬取小说（SSE 实时进度） |
| `/api/vocabs` | GET | 获取可用词库列表 |
| `/api/download` | GET | 下载爬取结果文件 |
| `/api/health` | GET | 健康检查 |
| `/api/system/info` | GET | 系统信息（最大线程数等） |

## 📁 项目结构

```
novel-study/
├── app.py                 # FastAPI Web API
├── main.py                # 核心处理流程
├── core/
│   ├── segmenter.py       # jieba 分词（并行优化）
│   ├── matcher.py         # Trie 关键词匹配
│   ├── annotator.py       # 内联注释生成
│   └── density.py         # 密度过滤（二分优化）
├── vocab/
│   ├── loader.py          # 词库加载器
│   └── data/              # CET-4 / CET-6 / 考研词库 JSON
├── scripts/
│   ├── fetch_novel.py     # 小说爬取脚本
│   ├── fetch_vocab.py     # 词库爬取脚本
│   └── validate_vocab.py  # 词库校验工具
├── static/
│   └── index.html         # Web 前端（单文件）
├── data/                  # 爬取的小说 / 测试文本
├── output/                # 注释结果输出
└── tests/                 # 单元测试（33 个）
```

## 🧪 运行测试

```bash
uv run pytest
```

## ⚠️ 免责声明

> **本工具仅供学习交流和个人研究使用。**

1. **版权尊重** — 本项目的爬取功能仅用于获取可公开访问的网页内容。用户应遵守目标网站的使用条款，尊重原作者版权。
2. **合理使用** — 请勿对目标站点发起高频请求或大规模爬取，避免对他人服务造成影响。
3. **内容免责** — 本工具不对爬取内容的合法性、准确性负责，用户需自行承担使用风险。
4. **反爬绕过** — 内置的 Cloudflare 绕过功能（cloudscraper）仅用于访问公开可读内容，不用于规避付费墙或登录限制。
5. **禁止商用** — 请勿将本工具用于任何商业用途或侵犯他人权益的行为。

**使用本工具即表示您已阅读并同意上述声明。**

## 🎯 适用场景

- 📚 英语学习者通过阅读中文小说自然积累词汇
- 🎓 备考 CET-4 / CET-6 / 考研英语的学生
- 📝 需要快速标注中文文本中高频词汇的研究者
- 🔤 对比中英文语境，加深单词记忆

## 📄 License

[MIT](LICENSE)
