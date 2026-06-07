"""
词库加载器

负责加载词库 JSON 文件，构建匹配用的关键词索引。
支持复合词扩展：将多个词条的中文关键词组合，生成新的匹配项。
"""

import json
from pathlib import Path

VOCAB_DATA_DIR = Path(__file__).parent / "data"

# 缓存：避免每次请求都重新读取 JSON 和构建索引
_vocab_cache: dict[str, dict[str, list[dict]]] = {}  # key="cet4,cet6,kaoyan" → keyword_map


def get_available_vocabs() -> dict[str, dict]:
    """获取所有可用词库信息。"""
    index_path = VOCAB_DATA_DIR / "index.json"
    if not index_path.exists():
        return {}
    with open(index_path, encoding="utf-8") as f:
        return json.load(f)


def load_vocab(names: list[str]) -> dict[str, list[dict]]:
    """
    加载指定词库，返回 {中文关键词: [词条信息, ...]} 映射表。
    支持复合词扩展。结果会被缓存。
    """
    cache_key = ",".join(sorted(names))
    if cache_key in _vocab_cache:
        return _vocab_cache[cache_key]

    keyword_map: dict[str, list[dict]] = {}
    entries_by_word: dict[str, dict] = {}  # 英文单词 → 词条

    for name in names:
        path = VOCAB_DATA_DIR / f"{name}.json"
        if not path.exists():
            print(f"[警告] 词库文件不存在: {path}")
            continue

        with open(path, encoding="utf-8") as f:
            entries = json.load(f)

        count = 0
        for entry in entries:
            entries_by_word[entry["word"].lower()] = entry
            for kw in entry.get("cn_keywords", []):
                keyword_map.setdefault(kw, []).append(entry)
                count += 1

        print(f"[词库] 已加载 {name}: {len(entries)} 词条, {count} 关键词映射")

    # 复合词扩展
    expanded = _expand_compound_keywords(keyword_map, entries_by_word)
    keyword_map.update(expanded)

    print(f"[词库] 关键词索引总数: {len(keyword_map)}（含 {len(expanded)} 个扩展复合词）")
    _vocab_cache[cache_key] = keyword_map
    return keyword_map


def _expand_compound_keywords(
    keyword_map: dict[str, list[dict]],
    entries_by_word: dict[str, dict],
) -> dict[str, list[dict]]:
    """
    复合词扩展：将相邻词条的中文关键词组合，生成新的匹配项。

    例如：
    - "wooden" 有关键词 "木制"，"bed" 有关键词 "床"
    - 组合生成 "木床" → wooden bed
    - "snake" 有关键词 "蛇"，"scorpion" 有关键词 "蝎子"
    - 组合生成 "蛇蝎" → snake and scorpion
    """
    # 常见的英文复合词/短语及其对应的中文复合形式
    # 手动维护，确保质量
    compound_rules = [
        # (英文词1, 英文词2, 中文复合词)
        ("wooden", "bed", "木床"),
        ("wooden", "door", "木门"),
        ("wooden", "chair", "木椅"),
        ("snake", "scorpion", "蛇蝎"),
        ("drive", "away", "驱赶"),
        ("peach", "branch", "桃枝"),
        ("old", "saying", "老话"),
        ("candle", "light", "烛光"),
    ]

    expanded: dict[str, list[dict]] = {}

    for en1, en2, cn_compound in compound_rules:
        if cn_compound in keyword_map:
            continue  # 已有，跳过

        entry1 = entries_by_word.get(en1.lower())
        entry2 = entries_by_word.get(en2.lower())

        if entry1 and entry2:
            # 创建一个复合词条：取第一个词的词条作为基础
            compound_entry = {
                "word": f"{en1} {en2}",
                "phonetic": "",
                "pos": entry1.get("pos", ""),
                "cn_meanings": [cn_compound],
                "cn_keywords": [cn_compound],
            }
            expanded[cn_compound] = [compound_entry]

    return expanded
