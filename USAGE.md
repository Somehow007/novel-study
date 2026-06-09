# Novel Study 使用文档

## 安装

### 一键安装

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

从 [GitHub Releases](https://github.com/Somehow007/novel-study/releases) 下载对应平台压缩包，解压后将可执行文件放到 PATH 目录中。

### 从源码运行

```bash
git clone https://github.com/Somehow007/novel-study.git
cd novel-study
curl -LsSf https://astral.sh/uv/install.sh | sh  # 安装 uv
uv sync                                            # 安装依赖
```

---

## CLI 命令 (`ns`)

### 爬取小说

```bash
# 基本用法
ns fetch https://www.example.com/book/12345/

# 指定章节范围
ns fetch <URL> --start 10 --end 50

# 多线程 + 断点续传
ns fetch <URL> --threads 5 --resume

# 使用代理
ns fetch <URL> --proxy http://127.0.0.1:7890

# 指定输出目录
ns fetch <URL> -o ~/novels/

# 调整请求间隔和批量写入
ns fetch <URL> --delay 1 --batch 100
```

输出默认在当前目录，生成 `data/<书名>/<书名>.txt`。

**参数说明：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--threads` | 并发线程数（超过系统上限自动调整） | 3 |
| `--delay` | 请求间隔（秒） | 0.5 |
| `--batch` | 每多少章写入一次文件 | 50 |
| `--start` / `--end` | 章节范围（从 1 开始，包含） | 全部 |
| `--resume` | 断点续传 | 关 |
| `--encoding` | 强制编码（如 gbk） | 自动检测 |
| `--proxy` | HTTP 代理 | 无 |
| `-o` | 输出目录 | 当前目录 |

### 注释文本

```bash
# 基本用法
ns annotate novel.txt

# 指定词库
ns annotate novel.txt --vocab cet6,kaoyan

# 调整密度
ns annotate novel.txt --min-score 2.0 --max-sentence 2 --max-chars 80

# 指定输出
ns annotate novel.txt -o annotated.txt --output-dir ~/output/

# 大文件并行
ns annotate novel.txt --parallel
```

**参数说明：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--vocab` | 词库，逗号分隔 | cet4,cet6,kaoyan |
| `--min-score` | 最低难度分数 | 1.5 |
| `--max-sentence` | 每句最多标注词数 | 3 |
| `--max-chars` | 字符窗口大小 | 100 |
| `--parallel` | 强制并行模式 | 自动判断 |
| `-o` | 输出文件名 | annotated_原文件名.txt |
| `--output-dir` | 输出目录 | 当前目录 |
| `-q` | 静默模式 | 关 |

### 词库管理

```bash
ns vocab list              # 查看所有词库
ns vocab info cet6         # 词库详情
```

### 配置管理

```bash
ns config init             # 交互式配置向导
ns config show             # 查看当前配置
ns config get <key>        # 获取单个值
ns config set <key> <val>  # 修改配置
ns config edit             # 用编辑器打开配置文件
ns config reset            # 重置默认
```

**可配置项：**

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `default_threads` | 默认爬取线程数 | 3 |
| `default_delay` | 默认请求间隔（秒） | 0.5 |
| `default_batch` | 多少章写入一次 | 50 |
| `default_vocab` | 默认词库 | cet4,cet6,kaoyan |
| `default_min_score` | 最低难度分 | 1.5 |
| `default_max_per_sentence` | 每句最多标注 | 3 |
| `default_max_per_chars` | 字符窗口 | 100 |
| `proxy` | HTTP 代理 | null |
| `output_dir` | 默认输出目录 | null（当前目录） |

### Web 服务

```bash
ns serve --port 8000       # 启动 Web 界面
```

浏览器打开 `http://localhost:8000`。

### 自更新

```bash
ns update                  # 拉取最新代码（源码模式）
```

---

## 配置文件

配置文件路径：`~/.novel-study/config.json`

示例：
```json
{
  "default_threads": 5,
  "default_delay": 0.3,
  "default_vocab": ["cet6", "kaoyan"],
  "default_min_score": 2.0,
  "proxy": "http://127.0.0.1:7890"
}
```

命令行参数优先级高于配置文件。

---

## 输出

- **爬取结果**：默认在当前目录下 `data/<书名>/<书名>.txt`
- **注释结果**：默认在当前目录下 `annotated_<原文件名>.txt`
- 可通过 `-o` / `--output-dir` 自定义输出位置

---

## 词库

| 词库 | 条目数 | 说明 |
|------|--------|------|
| cet4 | 4,499 | CET-4 基础词汇 |
| cet6 | 2,126 | CET-6 进阶词汇 |
| kaoyan | 5,101 | 考研高频词汇 |

---

## 构建发行版

需要在目标平台上构建（PyInstaller 不支持交叉编译）。

```bash
# 安装依赖 + PyInstaller
uv sync
uv pip install pyinstaller

# 构建
uv run pyinstaller ns.spec --noconfirm

# macOS / Linux：打包为 tar.gz
cd dist && tar czf ns-macos-arm64.tar.gz ns/

# Windows：打包为 zip
cd dist && Compress-Archive -Path ns -DestinationPath ns-windows-x64.zip
```

产物说明：

| 平台 | 构建机器 | 产物格式 |
|------|----------|---------|
| macOS arm64 | Mac (Apple Silicon) | `ns-macos-arm64.tar.gz` |
| macOS x64 | Mac (Intel) | `ns-macos-x64.tar.gz` |
| Linux x64 | Linux 服务器 | `ns-linux-x64.tar.gz` |
| Windows x64 | Windows 电脑 | `ns-windows-x64.zip` |

上传到 GitHub Releases：

```bash
gh release create v0.2.0 dist/ns-macos-arm64.tar.gz dist/ns-windows-x64.zip
```

---

## Web API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/annotate` | POST | 上传文件注释 |
| `/api/fetch/stream` | GET | 爬取小说（SSE） |
| `/api/vocabs` | GET | 词库列表 |
| `/api/system/info` | GET | 系统信息 |
| `/api/download` | GET | 下载文件 |
| `/api/health` | GET | 健康检查 |

---

## 运行测试

```bash
uv run python -m pytest tests/ -v
```
