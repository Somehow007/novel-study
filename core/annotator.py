"""
注释生成模块

根据匹配结果，在原文中插入内联英语注释。
基于精确位置（start/end）操作，避免替换偏移。
"""

from core.matcher import MatchResult


def annotate(text: str, matches: list[MatchResult]) -> str:
    """
    在原文中插入内联注释。

    格式：原文词(English[POS] 中文释义)

    基于 MatchResult 的精确位置（start/end），
    从后往前插入，避免位置偏移。
    """
    if not matches:
        return text

    # 按 start 降序排列，从后往前替换
    sorted_matches = sorted(matches, key=lambda m: m.start, reverse=True)

    result = text
    for m in sorted_matches:
        # 生成注释
        annotation = _format_annotation(m)
        # 替换原文中 [start:end] 的内容
        result = result[:m.start] + m.text + annotation + result[m.end:]

    return result


def _format_annotation(m: MatchResult) -> str:
    """格式化单个注释。"""
    entry = m.entry
    en_word = entry.get("word", "")
    pos = entry.get("pos", "")
    meanings = entry.get("cn_meanings", [])
    cn_display = "、".join(meanings[:2])

    parts = [en_word]
    if pos:
        parts.append(f"[{pos}]")
    parts.append(cn_display)

    return "(" + " ".join(parts) + ")"
