"""匹配模块单元测试。"""

import pytest
from core.segmenter import Token, init_jieba, segment
from core.matcher import Matcher, MatchResult


@pytest.fixture(autouse=True)
def setup():
    init_jieba("vocab/custom_dict.txt")


@pytest.fixture
def keyword_map():
    """构建测试用关键词映射。"""
    return {
        "蜡烛": [{"word": "candle", "pos": "n.", "cn_meanings": ["蜡烛"], "cn_keywords": ["蜡烛"]}],
        "少年": [{"word": "boy", "pos": "n.", "cn_meanings": ["少年"], "cn_keywords": ["少年"]}],
        "木床": [{"word": "wooden bed", "pos": "n.", "cn_meanings": ["木床"], "cn_keywords": ["木床"]}],
        "暮色": [{"word": "dusk", "pos": "n.", "cn_meanings": ["暮色"], "cn_keywords": ["暮色"]}],
        "僻静": [{"word": "secluded", "pos": "adj.", "cn_meanings": ["僻静"], "cn_keywords": ["僻静"]}],
    }


@pytest.fixture
def matcher(keyword_map):
    return Matcher(keyword_map)


class TestMatcher:
    def test_basic_match(self, matcher):
        tokens = segment("少年手持蜡烛")
        results = matcher.match(tokens)
        matched_words = [r.text for r in results]
        assert "少年" in matched_words
        assert "蜡烛" in matched_words

    def test_no_match_for_uncovered(self, matcher):
        tokens = segment("他走进了房间")
        results = matcher.match(tokens)
        # "房间"不在词库中，不应匹配
        matched_words = [r.text for r in results]
        assert "房间" not in matched_words

    def test_position_tracking(self, matcher):
        text = "暮色里，少年手持蜡烛"
        tokens = segment(text)
        results = matcher.match(tokens)
        for r in results:
            assert text[r.start:r.end] == r.text, (
                f"Position mismatch: '{r.text}' at [{r.start}:{r.end}], "
                f"got '{text[r.start:r.end]}'"
            )

    def test_compound_word_match(self, matcher):
        """复合词匹配：木床 应该作为一个整体匹配。"""
        tokens = segment("他躺在木床上")
        results = matcher.match(tokens)
        matched_words = [r.text for r in results]
        assert "木床" in matched_words

    def test_skip_punctuation(self, matcher):
        tokens = segment("少年，蜡烛")
        results = matcher.match(tokens)
        # 标点不应出现在匹配结果中
        for r in results:
            assert r.text not in ("，", "。", "、")

    def test_empty_tokens(self, matcher):
        results = matcher.match([])
        assert results == []
