"""
词义匹配模块

核心算法：基于 Trie 的中文关键词匹配 + 词性过滤 + 最长匹配优先 + 难度评分。
支持组合词匹配：当 jieba 将复合词拆开时，尝试组合相邻 token 重新匹配。
"""

from dataclasses import dataclass, field

from core.segmenter import Token


# ── 难度评分 ──────────────────────────────────────────────────────

LEVEL_SCORES = {
    "cet4": 1.0,    # 入门
    "cet6": 2.0,    # 进阶
    "kaoyan": 3.0,  # 高阶
    "ielts": 3.0,   # 高阶
}


def score_match(entry: dict) -> float:
    """
    计算匹配分数。分数越高越值得标注。

    评分维度：
    1. 词库等级（cet4=1, cet6=2, kaoyan/ielts=3）
    2. 词性加成（实词 +20%）
    3. 关键词长度惩罚（单字关键词 -50%，很可能是基础词）
    """
    # 基础分
    level = entry.get("level", "")
    base = LEVEL_SCORES.get(level, 1.0)

    # 词性加成：实词更值得标注
    pos = entry.get("pos", "")
    if pos.startswith(("n", "v", "a")):
        base *= 1.2

    # 关键词长度惩罚：单字关键词很可能是基础词
    kw_lengths = [len(kw) for kw in entry.get("cn_keywords", [])]
    avg_kw_len = sum(kw_lengths) / max(len(kw_lengths), 1)
    if avg_kw_len <= 1:
        base *= 0.5

    return round(base, 2)


# ── 数据结构 ──────────────────────────────────────────────────────

@dataclass
class MatchResult:
    """匹配结果。"""
    start: int              # 在原文中的起始位置
    end: int                # 在原文中的结束位置
    text: str               # 原文中的文本
    entry: dict             # 匹配到的词条信息
    score: float = 0.0      # 难度评分
    tokens: list[Token] = field(default_factory=list)  # 消耗的分词单元


class TrieNode:
    """Trie 前缀树节点。"""
    __slots__ = ['children', 'entries']

    def __init__(self):
        self.children: dict[str, 'TrieNode'] = {}
        self.entries: list[dict] = []  # 到达此节点的词条列表


# ── 匹配器 ────────────────────────────────────────────────────────

class Matcher:
    """词义匹配器。"""

    def __init__(self, keyword_map: dict[str, list[dict]]):
        self.keyword_map = keyword_map
        self.root = TrieNode()
        self._build_trie()

    def _build_trie(self) -> None:
        """将所有关键词构建为 Trie 结构。"""
        for keyword, entries in self.keyword_map.items():
            node = self.root
            for char in keyword:
                if char not in node.children:
                    node.children[char] = TrieNode()
                node = node.children[char]
            node.entries.extend(entries)

    def match(self, tokens: list[Token]) -> list[MatchResult]:
        """
        对分词结果进行匹配。

        策略：
        1. 跳过标点和虚词
        2. 尝试从当前位置开始，用 Trie 做最长匹配
        3. 同一位置多个候选 entry 时，选难度评分最高的
        4. 支持组合词：当单个 token 匹配后，继续尝试与后续 token 组合
        5. 一个 Token 只能被消耗一次

        返回所有命中的 MatchResult 列表（含 score）。
        """
        results = []
        i = 0

        while i < len(tokens):
            token = tokens[i]

            # 跳过标点和非实词
            if token.is_punctuation:
                i += 1
                continue

            # 尝试 Trie 最长匹配（支持组合词）
            match = self._try_match(tokens, i)
            if match:
                results.append(match)
                i += len(match.tokens)
            else:
                i += 1

        return results

    def _try_match(self, tokens: list[Token], start: int) -> MatchResult | None:
        """
        从 tokens[start] 开始，尝试 Trie 最长匹配。

        当同一 Trie 节点有多个 entry 时，选择难度评分最高的。
        """
        best_match = None
        best_len = 0

        node = self.root
        combined = ""

        for i in range(start, min(start + 8, len(tokens))):
            token = tokens[i]

            # 跳过标点（不参与组合）
            if token.is_punctuation:
                break

            # 逐字符走 Trie
            current_node = node
            found = True
            for char in token.word:
                if char in current_node.children:
                    current_node = current_node.children[char]
                else:
                    found = False
                    break

            if not found:
                break

            combined += token.word
            node = current_node

            # 检查是否有词条命中，选择评分最高的
            if current_node.entries:
                match_len = i - start + 1
                if match_len > best_len:
                    # 在所有候选 entry 中选评分最高的
                    best_entry = max(current_node.entries, key=score_match)
                    best_match = MatchResult(
                        start=tokens[start].start,
                        end=tokens[i].end,
                        text=combined,
                        entry=best_entry,
                        score=score_match(best_entry),
                        tokens=tokens[start:i + 1],
                    )
                    best_len = match_len

        return best_match
