# Novel Study 使用文档

## 环境准备

```bash
# 安装依赖（使用 uv）
uv sync

# 重新抓取词库（如需要）
uv run python scripts/fetch_vocab.py

# 校验词库格式
uv run python scripts/validate_vocab.py
```

## 运行处理

```bash
# 基本用法（处理 data/sample.txt，使用全部词库）
uv run python main.py

# 指定文件
uv run python main.py my_novel.txt

# 并行模式（大文件提速）
uv run python main.py my_novel.txt --parallel

# 自定义密度参数
uv run python main.py my_novel.txt --max-sentence=2 --max-chars=80 --min-score=2.0

# 参数说明
#   --parallel          并行分词（>100KB 文件推荐开启）
#   --max-sentence=N    每句话最多标注 N 个词（默认 3）
#   --max-chars=N       每 N 个字符内限制标注密度（默认 100）
#   --min-score=N       最低难度分数，低于此值不标注（默认 1.5）
```

## Web 界面

```bash
# 启动 Web 服务
uv run uvicorn app:app --host 0.0.0.0 --port 8001

# 浏览器访问
# http://localhost:8001
```

功能：文件拖拽上传、词库选择、密度参数调节、结果高亮预览、下载 txt

## 运行测试

```bash
uv run python -m pytest tests/ -v
```

## 输出

处理结果保存在 `output/` 目录，文件名格式：`annotated_{原文件名}.txt`

## 词库

| 词库 | 条目数 | 说明 |
|------|--------|------|
| cet4 | 4,499 | CET-4 基础词汇 |
| cet6 | 2,126 | CET-6 进阶词汇 |
| kaoyan | 5,101 | 考研高频词汇 |

词库数据位于 `vocab/data/`，自定义分词词典位于 `vocab/custom_dict.txt`。
