"""
注释密度控制模块

控制每句话、每段文字内的标注数量，避免注释过密影响阅读。
优先保留高难度词汇的标注，淘汰低难度的。
"""

import bisect
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
    """
    每个句子内按分数降序取 top N。

    优化：预排序 matches，用双指针分配到句子，避免每个句子遍历全部 matches。
    复杂度从 O(句子数×匹配数) 降到 O(匹配数×log(匹配数))。
    """
    if not matches:
        return []

    # 按位置排序，便于双指针扫描
    by_position = sorted(matches, key=lambda m: m.start)

    selected = []
    match_idx = 0
    n_matches = len(by_position)

    for sent_start, sent_end in sentences:
        # 跳过已经在之前句子范围内的 matches
        while match_idx < n_matches and by_position[match_idx].start < sent_start:
            match_idx += 1

        # 收集属于当前句子的 matches
        sent_matches = []
        j = match_idx
        while j < n_matches and by_position[j].start < sent_end:
            sent_matches.append(by_position[j])
            j += 1

        # 按分数降序取 top N
        if len(sent_matches) > max_per_sentence:
            sent_matches.sort(key=lambda m: m.score, reverse=True)
            sent_matches = sent_matches[:max_per_sentence]

        selected.extend(sent_matches)

    return selected


def _enforce_char_window(
    matches: list[MatchResult],
    max_per_chars: int,
) -> list[MatchResult]:
    """
    滑动字符窗口检查局部密度。

    优化：kept 列表按位置排序，用二分查找定位窗口边界，
    避免每个 match 遍历全部 kept。复杂度从 O(n²) 降到 O(n×log(n))。
    """
    if not matches:
        return []

    matches_sorted = sorted(matches, key=lambda m: m.start)
    limit = max_per_chars // 25  # 每25字符最多1个

    kept: list[MatchResult] = []
    kept_positions: list[int] = []  # 与 kept 平行，存储 start 位置

    for m in matches_sorted:
        window_start = max(0, m.start - max_per_chars)

        # 二分查找：找到 window_start 在 kept_positions 中的插入点
        lo = bisect.bisect_left(kept_positions, window_start)
        in_window_count = len(kept_positions) - lo

        if in_window_count < limit:
            # 窗口未满，直接插入（保持有序）
            insert_at = bisect.bisect_left(kept_positions, m.start)
            kept.insert(insert_at, m)
            kept_positions.insert(insert_at, m.start)
        else:
            # 窗口已满，和窗口内最低分比较
            weakest_idx = lo
            weakest_score = kept[lo].score
            for k in range(lo + 1, len(kept)):
                if kept[k].score < weakest_score:
                    weakest_score = kept[k].score
                    weakest_idx = k

            if m.score > weakest_score:
                # 替换最弱的
                del kept[weakest_idx]
                del kept_positions[weakest_idx]
                insert_at = bisect.bisect_left(kept_positions, m.start)
                kept.insert(insert_at, m)
                kept_positions.insert(insert_at, m.start)

    return kept
