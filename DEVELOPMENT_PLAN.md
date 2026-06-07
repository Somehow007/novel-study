# Novel Study 开发计划

> 小说英语词汇填充工具 — MVP 开发方案

## 项目目标

上传中文小说 txt 文件，系统自动根据选定词库（四六级/考研/雅思），在原文中内联插入英语单词注释，帮助用户在阅读小说的同时学习英语词汇。

注释格式：`原文词(English[POS] 中文释义)`

---

## 性能目标

| 文件大小 | 目标处理时间 | 说明 |
|----------|-------------|------|
| < 100KB | < 2 秒 | 短篇小说/单章 |
| 100KB ~ 1MB | < 10 秒 | 中篇小说 |
| 1MB ~ 5MB | < 30 秒 | 长篇小说 |
| 5MB ~ 10MB | < 60 秒 | 超长篇（并行模式） |

**约束条件**：
- 服务器配置：2 核 2G（当前云服务器规格）
- 内存峰值不超过文件大小的 3 倍

---

## 技术栈

| 层级 | 技术选型 | 理由 |
|------|----------|------|
| 后端框架 | FastAPI | 异步、自带文档、Python 生态 |
| 中文分词 | jieba | 成熟稳定、支持自定义词典 |
| 并行处理 | multiprocessing | 分段并行，2 核提速 ~1.8x |
| 前端 | 原生 HTML/CSS/JS | MVP 阶段够用，无需框架 |
| 部署 | Nginx + Uvicorn | 复用现有云服务器 |
| 数据存储 | 文件系统（JSON） | MVP 阶段无需数据库 |

---

## 项目结构

```
novel-study/
├── main.py                  # CLI 入口
├── app.py                   # FastAPI 应用入口（阶段三）
├── USAGE.md                 # 使用文档
├── DEVELOPMENT_PLAN.md      # 本文件
├── core/
│   ├── __init__.py
│   ├── segmenter.py         # 中文分词（jieba 封装 + 并行）
│   ├── matcher.py           # 词义匹配（Trie + 难度评分）
│   ├── annotator.py         # 注释生成（基于位置插入）
│   └── density.py           # 注释密度控制（句级限制 + 字符窗口）
├── vocab/
│   ├── loader.py            # 词库加载器（含复合词扩展）
│   ├── schema.json          # 词库 JSON Schema
│   ├── custom_dict.txt      # jieba 自定义词典
│   └── data/
│       ├── cet4.json        # CET-4 词库（~4500 条）
│       ├── cet6.json        # CET-6 词库（~2100 条）
│       ├── kaoyan.json      # 考研词库（~5100 条）
│       └── index.json       # 词库索引
├── static/                  # 前端文件（阶段三）
├── data/                    # 测试用小说文本
├── output/                  # 生成的注释文件
├── tests/
│   ├── test_segmenter.py
│   ├── test_matcher.py
│   ├── test_annotator.py
│   └── test_density.py
└── scripts/
    ├── fetch_vocab.py       # 词库抓取脚本
    └── validate_vocab.py    # 词库格式校验
```

---

## 阶段一：词库建设 ✅

**目标**：构建统一格式、带难度等级的多词库数据

### 1.1 词库数据格式

```json
{
  "word": "porcelain",
  "phonetic": "/ˈpɔːrsəlɪn/",
  "pos": "n.",
  "cn_meanings": ["瓷器"],
  "cn_keywords": ["瓷器", "瓷"],
  "level": "kaoyan"
}
```

| 字段 | 说明 |
|------|------|
| `word` | 英文单词/短语 |
| `phonetic` | 音标 |
| `pos` | 词性 |
| `cn_meanings` | 中文释义列表 |
| `cn_keywords` | 中文关键词（用于反向匹配小说文本） |
| `level` | 词库等级：`cet4` / `cet6` / `kaoyan` / `ielts` |

### 1.2 词库来源

| 词库 | 条目数 | level | 数据源 |
|------|--------|-------|--------|
| CET-4 | 4,499 | `cet4` | 有道词典（3 源合并） |
| CET-6 | 2,126 | `cet6` | mahavivo/english-wordlists |
| 考研 | 5,101 | `kaoyan` | mahavivo/english-wordlists |

抓取脚本 `scripts/fetch_vocab.py`：
- 支持有道 zip 格式 + mahavivo 文本格式
- 多源合并去重
- 自动生成压缩关键词（去掉"的、与、之"等虚词）
- 自动写入 `level` 字段

### 1.3 自定义词典 `vocab/custom_dict.txt`

- 小说领域专有名词（泥瓶巷、龙窑、陈平安）
- 高频组合词（木床、蛇蝎、桃枝、暮色、僻静）
- 频率设置确保 jieba 优先采用（如 "木床 50 n"）

### 验收标准

| 标准 | 状态 |
|------|------|
| CET-4 词库 ≥ 4500 条 | ✅ 4,499 条 |
| 词库格式通过 JSON Schema 校验 | ✅ `validate_vocab.py` 全部通过 |
| 每条数据含 `level` 字段 | ✅ |
| 抓取脚本可复现运行 | ✅ |
| 自定义词典覆盖小说高频词 | ✅ |

---

## 阶段二：核心引擎 ✅

**目标**：高质量分词、匹配、注释，支持难度评分和密度控制

### 2.1 分词模块 `core/segmenter.py`

- 封装 jieba，加载自定义词典
- Token 带精确位置（start/end），支持位置校验
- `segment_parallel()` 多进程并行分词（大文件提速 ~1.8x）

### 2.2 匹配模块 `core/matcher.py`

**算法**：Trie 前缀树 + 最长匹配优先 + 难度评分

```
流程：Trie 逐字符匹配 → 多候选 entry → score_match() 选最优
```

**难度评分 `score_match(entry)`**：

| 维度 | 规则 | 说明 |
|------|------|------|
| 词库等级 | cet4=1.0, cet6=2.0, kaoyan=3.0 | 基础分 |
| 词性加成 | n/v/a × 1.2 | 实词更值得标注 |
| 关键词长度 | 平均长度 ≤ 1 字 → × 0.5 | 单字关键词降权 |

**组合词支持**：jieba 拆开的相邻 token 自动组合重新匹配（如 "木"+"床" → "木床"）

### 2.3 注释模块 `core/annotator.py`

- 基于 MatchResult 的精确位置（start/end）插入注释
- 从后往前替换，无偏移问题
- 格式：`(English [POS] 中文释义1、中文释义2)`

### 2.4 密度控制 `core/density.py`

**三层过滤**：

| 层级 | 参数 | 默认值 | 说明 |
|------|------|--------|------|
| 最低分数 | `min_score` | 1.5 | 低于此分数直接丢弃（过滤 CET-4 基础词） |
| 句级限制 | `max_per_sentence` | 3 | 每句话最多标注 N 个 |
| 字符窗口 | `max_per_chars` | 100 | 每 100 字符内最多标注 N/25 个 |

**效果**：171 个匹配 → 过滤后 65 个（过滤率 62%），阅读体验显著提升。

### 2.5 性能优化

| 策略 | 说明 | 效果 |
|------|------|------|
| Trie 前缀树 | 关键词索引从 O(n×m) 降为 O(n) | 万级词库毫秒级匹配 |
| multiprocessing | 按段落并行分词 | 1MB 文件 7.6s（< 10s 达标） |
| jieba 单例 | 全局复用，避免重复加载 | 节省 ~0.3s 冷启动 |

### 验收标准

| 标准 | 状态 |
|------|------|
| "木床" 整体匹配 | ✅ |
| 注释位置准确，无偏移 | ✅ |
| 难度评分区分 CET-4 和考研词汇 | ✅ |
| 密度过滤减少 60%+ 标注 | ✅ |
| 单元测试覆盖核心场景 | ✅ 33 个测试全通过 |
| 1MB 文件 < 10 秒 | ✅ 7.63 秒 |

---

## 阶段三：Web 界面 ✅

**目标**：提供可用的 Web 上传界面

### 3.1 后端 API `app.py`

```
POST /api/annotate
  参数：file, vocab, max_per_sentence, max_per_chars, min_score
  同步返回 JSON { result, stats, filename }

GET /api/vocabs                    → 词库列表
GET /api/health                    → 服务状态
```

- 并发控制：`asyncio.Semaphore(2)` 保护 2 核 2G 服务器
- 文件限制：10MB，UTF-8 编码校验
- 大文件自动启用并行分词（>100KB）

### 3.2 前端页面 `static/index.html`

单文件 HTML（CSS/JS 内联），功能：
- 文件拖拽上传
- 词库复选框（从 API 动态加载）
- 密度参数滑块（每句上限、字符窗口、最低难度分）
- 结果预览（注释高亮显示）
- 下载 txt 文件
- 处理统计（总词数、匹配数、过滤率）

### 3.3 核心重构 `main.py`

提取 `process_text(text, vocab_names, ...)` 函数，返回 `{result, stats}`，供 Web API 和 CLI 共用。

### 验收标准

| 标准 | 状态 |
|------|------|
| 上传 txt → 返回带注释文本 | ✅ |
| 支持多词库 + 密度参数 | ✅ |
| 支持最大 10MB 文件 | ✅ |
| 结果可预览、可下载 | ✅ |
| 并发保护（信号量） | ✅ |

---

## 阶段四：部署上线（待开发）

**目标**：部署到云服务器，提供在线访问

### Nginx 配置

```nginx
server {
    listen 80;
    server_name _;

    location / {
        root /var/www/novel-study/static;
        index index.html;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        client_max_body_size 10m;
        proxy_read_timeout 120s;
    }
}
```

### 验收标准

| 标准 | 状态 |
|------|------|
| 通过 http://124.222.65.169 可访问 | 待开发 |
| 端到端流程可用 | 待开发 |
| 进程自动重启 | 待开发 |

---

## 已知风险与应对

| 风险 | 影响 | 应对策略 | 状态 |
|------|------|----------|------|
| 分词不准导致误标 | 中 | 自定义词典（高频 50） | ✅ 已缓解 |
| 词库关键词覆盖不全 | 高 | 压缩关键词生成 + 复合词扩展 | ✅ 已缓解 |
| 注释过多影响阅读 | 高 | 密度控制（句级 + 字符窗口 + 最低分） | ✅ 已解决 |
| 基础词干扰学习 | 高 | 难度评分（cet4 低分自动过滤） | ✅ 已解决 |
| MB 级文件处理超时 | 高 | Trie + 并行分词 | ✅ 已解决 |
| 并发请求拖垮服务器 | 中 | asyncio.Semaphore(2) 控制 | ✅ 已解决 |
