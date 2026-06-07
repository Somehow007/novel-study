"""
中文分词模块

封装 jieba，提供结构化的分词结果。
支持并行分词以提升大文件处理性能。
"""

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

import jieba
import jieba.posseg as pseg


@dataclass
class Token:
    """分词结果单元。"""
    word: str       # 词语
    flag: str       # 词性标记（jieba 标注）
    start: int      # 在原文中的起始位置
    end: int        # 在原文中的结束位置

    @property
    def is_content_word(self) -> bool:
        """是否为实词（参与匹配的词性）。"""
        return self.flag[0] in {'n', 'v', 'a', 'd', 'i', 'j', 'l', 'b'}

    @property
    def is_punctuation(self) -> bool:
        """是否为标点或特殊符号。"""
        return self.flag == 'x' or not any(
            '\u4e00' <= c <= '\u9fff' or c.isalpha() for c in self.word
        )


# jieba 单例，避免重复初始化
_initialized = False
_custom_dict_path: str | None = None


def init_jieba(custom_dict_path: str | None = None) -> None:
    """初始化 jieba，加载自定义词典。只需调用一次。"""
    global _initialized, _custom_dict_path
    _custom_dict_path = custom_dict_path
    if _initialized:
        return
    if custom_dict_path:
        jieba.load_userdict(custom_dict_path)
    _initialized = True


def segment(text: str) -> list[Token]:
    """
    对文本进行分词和词性标注。

    返回 Token 列表，每个 Token 记录了在原文中的精确位置。
    使用增量位置追踪，避免 O(n) 的 text.find() 调用。
    """
    tokens = []
    pos = 0
    text_len = len(text)

    for word, flag in pseg.cut(text):
        wlen = len(word)

        # 快速路径：当前位置精确匹配（jiba 输出连续覆盖原文）
        if pos < text_len and text[pos:pos + wlen] == word:
            start = pos
        else:
            # 回退：仅在不匹配时才 search（极端边界情况）
            start = text.find(word, pos)
            if start == -1:
                start = pos

        end = start + wlen
        tokens.append(Token(word=word, flag=flag, start=start, end=end))
        pos = end

    return tokens


def _init_worker(dict_path: str | None) -> None:
    """子进程初始化函数。"""
    if dict_path:
        jieba.load_userdict(dict_path)


def _segment_batch(texts: list[str]) -> list[tuple[int, list[Token]]]:
    """子进程批量分词函数。返回 [(index, tokens), ...]。"""
    return [(i, segment(t)) for i, t in enumerate(texts)]


def segment_parallel(texts: list[str], max_workers: int = 2,
                     batch_size: int = 200) -> list[list[Token]]:
    """
    并行分词多个段落。

    将段落分批提交给子进程，减少进程间通信开销。
    对于小文件，直接串行处理（避免进程启动开销）。
    """
    total_chars = sum(len(t) for t in texts)

    # 小文件直接串行
    if len(texts) < 20 or total_chars < 100_000:
        return [segment(t) for t in texts]

    # 分批：每 batch_size 个段落为一组
    batches = []
    for i in range(0, len(texts), batch_size):
        batches.append(texts[i:i + batch_size])

    # 并行处理每个批次
    all_results: list[list[Token]] = [None] * len(texts)  # type: ignore

    with ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=_init_worker,
        initargs=(_custom_dict_path,),
    ) as executor:
        batch_offset = 0
        for batch_results in executor.map(_segment_batch, batches):
            for local_idx, tokens in batch_results:
                all_results[batch_offset + local_idx] = tokens
            batch_offset += len(batch_results)

    return all_results
