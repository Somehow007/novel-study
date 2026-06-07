"""分词模块单元测试。"""

import pytest
from core.segmenter import Token, init_jieba, segment


@pytest.fixture(autouse=True)
def setup():
    """初始化 jieba。"""
    init_jieba()


class TestToken:
    def test_is_content_word(self):
        t = Token(word="蜡烛", flag="n", start=0, end=2)
        assert t.is_content_word is True

    def test_is_not_content_word(self):
        t = Token(word="的", flag="uj", start=0, end=1)
        assert t.is_content_word is False

    def test_is_punctuation(self):
        t = Token(word="，", flag="x", start=0, end=1)
        assert t.is_punctuation is True

    def test_is_not_punctuation(self):
        t = Token(word="少年", flag="n", start=0, end=2)
        assert t.is_punctuation is False


class TestSegment:
    def test_basic_segment(self):
        tokens = segment("蜡烛照亮了房间")
        words = [t.word for t in tokens]
        assert "蜡烛" in words
        assert "照亮" in words

    def test_positions_are_correct(self):
        text = "暮色里，小镇名叫泥瓶巷"
        tokens = segment(text)
        for t in tokens:
            assert text[t.start:t.end] == t.word, (
                f"Position mismatch: {t.word} at [{t.start}:{t.end}]"
            )

    def test_compound_words_not_split(self):
        """自定义词典中的复合词不应被拆分。"""
        tokens = segment("木床、蛇蝎、桃枝")
        words = [t.word for t in tokens]
        assert "木床" in words
        assert "蛇蝎" in words
        assert "桃枝" in words

    def test_empty_text(self):
        tokens = segment("")
        assert tokens == []
