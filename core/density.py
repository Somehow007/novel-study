"""
注释密度控制模块

控制每句话、每段文字内的标注数量，避免注释过密影响阅读。
优先保留高难度词汇的标注，淘汰低难度的。
"""

import re

from core.matcher import MatchResult

# 中文句子结束标点
SENTENCE_END = re.compile(r'([。！？；…]+|[.!?;]+)')


def filter_by_density(
    text: str,
    matches: list[MatchResult],
    max_per_sentence: int = 3,
    max_per_chars: int = 100,
    min_score: float = 1.5,
) -> list[MatchResult]:
    """
    按密度控制过滤匹配结果。

    策略：
    1. 按 min_score 过滤低分匹配（低于阈值直接丢弃）
    2. 按句子分组，每句内按分数降序排列，取 top N
    3. 滑动字符窗口检查局部密度

    参数：
        text: 原文
        matches: 所有匹配结果
        max_per_sentence: 每句话最多保留几个标注
        max_per_chars: 每 N 个字符内最多保留几个标注
        min_score: 最低分数阈值（低于此分数直接跳过）

    返回：过滤后的匹配结果列表
    """
    if not matches:
        return []

    # 第一步：按最低分数过滤
    candidates = [m for m in matches if m.score >= min_score]
    if not candidates:
        return []

    # 第二步：按句子分组，每句内限制数量
    sentences = _split_sentences(text)
    selected = _select_per_sentence(sentences, candidates, max_per_sentence)

    # 第三步：滑动窗口检查局部密度
    selected = _enforce_char_window(selected, max_per_chars)

    return selected


def _split_sentences(text: str) -> list[tuple[int, int]]:
    """
    将文本切分为句子。返回 [(start, end), ...] 列表。
    句子边界：。！？；… 等标点。
    """
    sentences = []
    last_end = 0

    for m in SENTENCE_END.finditer(text):
        sent_end = m.end()
        sentences.append((last_end, sent_end))
        last_end = sent_end

    # 最后一段
    if last_end < len(text):
        sentences.append((last_end, len(text)))

    return sentences


def _select_per_sentence(
    sentences: list[tuple[int, int]],
    matches: list[MatchResult],
    max_per_sentence: int,
) -> list[MatchResult]:
    """每个句子内按分数降序取 top N。"""
    selected = []

    for sent_start, sent_end in sentences:
        # 找出属于这个句子的匹配
        sent_matches = [
            m for m in matches
            if m.start >= sent_start and m.start < sent_end
        ]
        # 按分数降序排列，取 top N
        sent_matches.sort(key=lambda m: m.score, reverse=True)
        selected.extend(sent_matches[:max_per_sentence])

    return selected


def _enforce_char_window(
    matches: list[MatchResult],
    max_per_chars: int,
) -> list[MatchResult]:
    """
    滑动字符窗口检查局部密度。

    对于每个匹配，检查它前面 max_per_chars 个字符内
    已经有多少个被选中的匹配。如果超过限制，淘汰分数最低的。
    """
    if not matches:
        return []

    # 按位置排序
    matches_sorted = sorted(matches, key=lambda m: m.start)

    # 贪心选择：保留列表
    kept: list[MatchResult] = []
    kept_set: set[int] = set()  # 用 id 标记

    for m in matches_sorted:
        # 计算窗口内已有的匹配数
        window_start = max(0, m.start - max_per_chars)
        in_window = [k for k in kept if k.start >= window_start]

        if len(in_window) < max_per_chars // 25:  # 粗略：每25字符最多1个
            kept.append(m)
            kept_set.add(id(m))
        else:
            # 窗口满了，和窗口内最低分的比较
            in_window.sort(key=lambda x: x.score)
            weakest = in_window[0]
            if m.score > weakest.score:
                # 替换最弱的
                kept.remove(weakest)
                kept.append(m)

    return kept
