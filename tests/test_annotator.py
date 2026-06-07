"""注释模块单元测试。"""

import pytest
from core.annotator import annotate, _format_annotation
from core.matcher import MatchResult


class TestFormatAnnotation:
    def test_basic_format(self):
        m = MatchResult(
            start=0, end=2, text="蜡烛",
            entry={"word": "candle", "pos": "n.", "cn_meanings": ["蜡烛"]},
        )
        result = _format_annotation(m)
        assert result == "(candle [n.] 蜡烛)"

    def test_multiple_meanings(self):
        m = MatchResult(
            start=0, end=2, text="少年",
            entry={"word": "boy", "pos": "n.", "cn_meanings": ["男孩", "少年"]},
        )
        result = _format_annotation(m)
        assert result == "(boy [n.] 男孩、少年)"

    def test_no_pos(self):
        m = MatchResult(
            start=0, end=2, text="蜡烛",
            entry={"word": "candle", "pos": "", "cn_meanings": ["蜡烛"]},
        )
        result = _format_annotation(m)
        assert result == "(candle 蜡烛)"


class TestAnnotate:
    def test_basic_annotate(self):
        text = "少年手持蜡烛"
        matches = [
            MatchResult(start=0, end=2, text="少年",
                        entry={"word": "boy", "pos": "n.", "cn_meanings": ["少年"]}),
            MatchResult(start=4, end=6, text="蜡烛",
                        entry={"word": "candle", "pos": "n.", "cn_meanings": ["蜡烛"]}),
        ]
        result = annotate(text, matches)
        assert "少年(boy [n.] 少年)" in result
        assert "蜡烛(candle [n.] 蜡烛)" in result

    def test_preserves_unmatched_text(self):
        text = "他走进了房间，点燃了蜡烛"
        matches = [
            MatchResult(start=10, end=12, text="蜡烛",
                        entry={"word": "candle", "pos": "n.", "cn_meanings": ["蜡烛"]}),
        ]
        result = annotate(text, matches)
        assert result.startswith("他走进了房间，点燃了")
        assert "蜡烛(candle [n.] 蜡烛)" in result

    def test_no_matches(self):
        text = "他走进了房间"
        result = annotate(text, [])
        assert result == text

    def test_adjacent_matches(self):
        """非相邻的匹配不应互相干扰，中间的字应保留。"""
        text = "暮色里少年"  # 暮色=[0:2], 里=[2:3], 少年=[3:5]
        matches = [
            MatchResult(start=0, end=2, text="暮色",
                        entry={"word": "dusk", "pos": "n.", "cn_meanings": ["暮色"]}),
            MatchResult(start=3, end=5, text="少年",
                        entry={"word": "boy", "pos": "n.", "cn_meanings": ["少年"]}),
        ]
        result = annotate(text, matches)
        assert "暮色(dusk [n.] 暮色)" in result
        assert "少年(boy [n.] 少年)" in result
        assert "里" in result  # 中间的"里"应保留
