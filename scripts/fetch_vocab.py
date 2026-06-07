"""
词库抓取脚本

支持的数据源：
1. mahavivo/english-wordlists - CET6、考研 (文本格式)
2. kajweb/dict (有道) - CET4 (JSON格式，zip压缩)

输出：vocab/data/{name}.json，统一格式
"""

import io
import json
import re
import sys
import zipfile
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── 数据源配置 ──────────────────────────────────────────────────

SOURCES = {
    "cet4": {
        "urls": [
            {
                "url": "http://ydschool-online.nos.netease.com/1521164649209_CET4_1.zip",
                "format": "youdao_zip",
                "zip_inner": "CET4_1.json",
            },
            {
                "url": "http://ydschool-online.nos.netease.com/1521164635506_CET4_2.zip",
                "format": "youdao_zip",
                "zip_inner": "CET4_2.json",
            },
            {
                "url": "http://ydschool-online.nos.netease.com/1521164643060_CET4_3.zip",
                "format": "youdao_zip",
                "zip_inner": "CET4_3.json",
            },
        ],
        "description": "CET-4 词汇（有道+新东方合并）",
    },
    "cet6": {
        "urls": [
            {
                "url": "https://cdn.jsdelivr.net/gh/mahavivo/english-wordlists@master/CET6_edited.txt",
                "format": "mahavivo",
            },
        ],
        "description": "CET-6 词汇",
    },
    "kaoyan": {
        "urls": [
            {
                "url": "https://cdn.jsdelivr.net/gh/mahavivo/english-wordlists@master/NPEE_Wordlist.txt",
                "format": "mahavivo",
            },
        ],
        "description": "考研词汇",
    },
}

OUTPUT_DIR = PROJECT_ROOT / "vocab" / "data"


# ── 解析器：mahavivo 文本格式 ───────────────────────────────────

def parse_mahavivo_line(line: str) -> dict | None:
    """
    解析 mahavivo 格式的一行：
    abandon [əˈbændən] v. 1. 抛弃，放弃 2. 离弃...
    abandon [əˈbændən] vt.离弃,丢弃;遗弃,抛弃;放弃
    """
    line = line.strip()
    if not line:
        return None

    m = re.match(
        r'^([a-zA-Z][a-zA-Z\s\-\']*?)\s+'
        r'\[([^\]]+)\]\s+'
        r'([a-z]+\.)?\s*'
        r'(.+)$',
        line
    )
    if not m:
        return None

    word = m.group(1).strip()
    phonetic = m.group(2).strip()
    pos = m.group(3) or ""
    meaning_text = m.group(4).strip()

    cn_meanings = extract_cn_meanings(meaning_text)
    if not cn_meanings:
        return None

    cn_keywords = generate_keywords(cn_meanings, meaning_text)

    return {
        "word": word,
        "phonetic": f"/{phonetic}/",
        "pos": pos,
        "cn_meanings": cn_meanings,
        "cn_keywords": cn_keywords,
    }


# ── 解析器：有道 JSON 格式 ─────────────────────────────────────

def parse_youdao_entry(entry: dict) -> dict | None:
    """
    解析有道词典格式的一个词条。
    """
    word = entry.get("headWord", "")
    if not word:
        return None

    content = entry.get("content", {}).get("word", {}).get("content", {})

    # 音标
    phonetic = content.get("usphone", "") or content.get("ukphone", "")

    # 释义
    trans = content.get("trans", [])
    pos_list = []
    cn_meanings = []

    for t in trans:
        p = t.get("pos", "").strip()
        meaning = t.get("tranCn", "").strip()
        if meaning:
            # 清理释义中的标记如 [计] [力]
            meaning = re.sub(r'\[[^\]]*\]', '', meaning).strip()
            if meaning:
                cn_meanings.append(meaning)
                if p and p not in pos_list:
                    pos_list.append(p)

    if not cn_meanings:
        return None

    pos = "/".join(pos_list) if pos_list else ""
    raw_text = "; ".join(cn_meanings)
    cn_keywords = generate_keywords(cn_meanings, raw_text)

    return {
        "word": word,
        "phonetic": f"/{phonetic}/" if phonetic else "",
        "pos": pos,
        "cn_meanings": cn_meanings,
        "cn_keywords": cn_keywords,
    }


# ── 通用工具 ──────────────────────────────────────────────────

def extract_cn_meanings(text: str) -> list[str]:
    """从释义文本中提取中文释义。"""
    text = re.sub(r'\d+\.\s*', '', text)
    parts = re.split(r'[;；,，]', text)

    meanings = []
    for part in parts:
        part = part.strip()
        if re.search(r'[\u4e00-\u9fff]', part):
            core = re.sub(r'\([^)]*\)', '', part).strip()
            if core:
                meanings.append(core)
            elif part:
                meanings.append(part)

    return meanings[:5]


def generate_keywords(meanings: list[str], raw_text: str) -> list[str]:
    """从中文释义生成关键词列表。"""
    keywords = set()

    for meaning in meanings:
        # 拆分出核心词
        sub_parts = re.split(r'[、，,;/；]', meaning)
        for part in sub_parts:
            part = part.strip()
            # 过滤：至少2个中文字符，不含英文，不含"等"结尾
            if (len(part) >= 2
                    and re.search(r'[\u4e00-\u9fff]', part)
                    and not re.search(r'[a-zA-Z]', part)
                    and not part.endswith('等')):
                keywords.add(part)

    # 从原始文本中提取括号内的短补充说明
    brackets = re.findall(r'\(([^)]+)\)', raw_text)
    for b in brackets:
        b = b.strip()
        if (re.search(r'[\u4e00-\u9fff]', b)
                and 2 <= len(b) <= 6
                and not re.search(r'[a-zA-Z]', b)):
            keywords.add(b)

    # 生成压缩形式：去掉常见虚词，保留实词组合
    # 如 "木制的床" → "木床"，"蛇与蝎子" → "蛇蝎"
    FILLER_CHARS = set('的了着过与和之')
    compressed = set()
    for kw in list(keywords):
        if len(kw) <= 2:
            continue
        # 去掉虚词字符
        stripped = ''.join(c for c in kw if c not in FILLER_CHARS)
        if 2 <= len(stripped) <= 4 and stripped != kw:
            compressed.add(stripped)
    keywords.update(compressed)

    return sorted(keywords)


# ── 主流程 ──────────────────────────────────────────────────────

def fetch_one_source(source_item: dict) -> list[dict]:
    """下载并解析一个数据源，返回词条列表。"""
    import urllib.request

    url = source_item["url"]
    fmt = source_item["format"]

    print(f"  下载: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except Exception as e:
        print(f"  [错误] 下载失败: {e}")
        return []

    print(f"  文件大小: {len(raw)} bytes")

    entries = []

    if fmt == "youdao_zip":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                inner_name = source_item.get("zip_inner", "")
                if inner_name:
                    text = zf.read(inner_name).decode("utf-8")
                else:
                    names = zf.namelist()
                    text = zf.read(names[0]).decode("utf-8")
        except Exception as e:
            print(f"  [错误] 解压失败: {e}")
            return []

        for line in text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            try:
                entry = parse_youdao_entry(json.loads(line))
                if entry:
                    entries.append(entry)
            except json.JSONDecodeError:
                continue

    elif fmt == "mahavivo":
        text = None
        for enc in ["utf-8", "gbk", "gb2312"]:
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            print(f"  [错误] 无法解码文件")
            return []

        text = text.replace('\r\n', '\n').replace('\r', '\n')
        for line in text.split('\n'):
            entry = parse_mahavivo_line(line)
            if entry:
                entries.append(entry)

    print(f"  解析: {len(entries)} 词条")
    return entries


def fetch_and_convert(name: str, source: dict) -> int:
    """下载并转换一个词库（支持多源合并）。返回词条数。"""
    print(f"\n[{name}] {source['description']}")

    all_entries = []
    for source_item in source["urls"]:
        entries = fetch_one_source(source_item)
        all_entries.extend(entries)

    # 去重（保留先出现的），过滤无效条目，添加 level
    seen = set()
    unique_entries = []
    for e in all_entries:
        key = e["word"].lower()
        if key in seen:
            continue
        # 过滤：必须有 cn_meanings 和 cn_keywords
        if not e.get("cn_meanings") or not e.get("cn_keywords"):
            continue
        seen.add(key)
        e["level"] = name  # 标记词库来源等级
        unique_entries.append(e)

    print(f"  合并去重: {len(all_entries)} → {len(unique_entries)} 词条")

    # 输出
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{name}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(unique_entries, f, ensure_ascii=False, indent=2)

    print(f"  已保存: {output_path}")
    return len(unique_entries)


def main():
    """抓取所有配置的词库。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    results = {}

    for name, source in SOURCES.items():
        count = fetch_and_convert(name, source)
        results[name] = count
        total += count

    print(f"\n{'='*50}")
    print(f"抓取完成！总计 {total} 词条")
    for name, count in results.items():
        print(f"  {name}: {count} 词条")
    print(f"{'='*50}")

    # 生成词库索引
    index = {
        name: {
            "file": f"{name}.json",
            "count": count,
            "description": SOURCES[name]["description"],
        }
        for name, count in results.items()
        if count > 0
    }
    index_path = OUTPUT_DIR / "index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"\n词库索引已保存: {index_path}")


if __name__ == "__main__":
    main()
