"""密度控制和难度评分单元测试。"""

import pytest
from core.density import filter_by_density, _split_sentences
from core.matcher import MatchResult, score_match


class TestScoreMatch:
    def test_cet4_low_score(self):
        entry = {"word": "place", "pos": "n.", "cn_keywords": ["地方"], "level": "cet4"}
        score = score_match(entry)
        assert score <= 1.5  # CET-4 应该低分

    def test_kaoyan_high_score(self):
        entry = {"word": "porcelain", "pos": "n.", "cn_keywords": ["瓷器"], "level": "kaoyan"}
        score = score_match(entry)
        assert score >= 2.5  # 考研应该高分

    def test_cet6_medium_score(self):
        entry = {"word": "abandon", "pos": "v.", "cn_keywords": ["抛弃"], "level": "cet6"}
        score = score_match(entry)
        assert 1.5 <= score <= 3.0

    def test_single_char_keyword_penalty(self):
        """单字关键词应该被降权。"""
        entry_easy = {"word": "a", "pos": "art.", "cn_keywords": ["一"], "level": "kaoyan"}
        entry_hard = {"word": "abandon", "pos": "v.", "cn_keywords": ["抛弃", "放弃"], "level": "kaoyan"}
        assert score_match(entry_easy) < score_match(entry_hard)

    def test_content_word_bonus(self):
        """实词应该比虚词得分高。"""
        entry_noun = {"word": "cat", "pos": "n.", "cn_keywords": ["猫"], "level": "cet4"}
        entry_conj = {"word": "and", "pos": "conj.", "cn_keywords": ["和"], "level": "cet4"}
        assert score_match(entry_noun) > score_match(entry_conj)


class TestSplitSentences:
    def test_basic_split(self):
        text = "第一句话。第二句话！"
        sentences = _split_sentences(text)
        assert len(sentences) == 2

    def test_no_ending_punctuation(self):
        text = "没有结尾标点的一段话"
        sentences = _split_sentences(text)
        assert len(sentences) == 1

    def test_multiple_punctuation(self):
        text = "你好！再见？结束。"
        sentences = _split_sentences(text)
        assert len(sentences) == 3


class TestFilterByDensity:
    def _make_match(self, start, end, score):
        return MatchResult(
            start=start, end=end,
            text="test",
            entry={"word": "test", "pos": "n.", "cn_meanings": ["测试"]},
            score=score,
        )

    def test_filter_low_score(self):
        """低于 min_score 的匹配应该被过滤。"""
        text = "这是一句话。"
        matches = [
            self._make_match(0, 2, score=1.0),  # 低于阈值
            self._make_match(2, 4, score=3.0),  # 高于阈值
        ]
        result = filter_by_density(text, matches, min_score=1.5)
        assert len(result) == 1
        assert result[0].score == 3.0

    def test_limit_per_sentence(self):
        """每句话的标注数应该受限制。"""
        text = "一句话里有很多词需要标注。"
        matches = [
            self._make_match(0, 2, score=3.0),
            self._make_match(2, 4, score=2.5),
            self._make_match(4, 6, score=2.0),
            self._make_match(6, 8, score=1.8),
        ]
        result = filter_by_density(text, matches, max_per_sentence=2, min_score=0)
        assert len(result) == 2
        # 应该保留分数最高的两个
        scores = sorted([r.score for r in result], reverse=True)
        assert scores == [3.0, 2.5]

    def test_empty_matches(self):
        result = filter_by_density("任何文本", [], min_score=0)
        assert result == []

    def test_all_below_threshold(self):
        text = "一句话。"
        matches = [self._make_match(0, 2, score=0.5)]
        result = filter_by_density(text, matches, min_score=1.5)
        assert result == []
