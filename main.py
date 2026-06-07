"""
小说英语词汇填充工具

核心流程：中文文本 → 分词 → 匹配 → 评分 → 密度过滤 → 注释输出
"""

from pathlib import Path

from core.annotator import annotate
from core.density import filter_by_density
from core.matcher import Matcher
from core.segmenter import init_jieba, segment, segment_parallel
from vocab.loader import load_vocab

# ── 配置 ──────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_DIR = Path(__file__).parent / "output"


# ── 主流程 ────────────────────────────────────────────────────────

def process_text(
    text: str,
    vocab_names: list[str],
    parallel: bool = False,
    max_per_sentence: int = 3,
    max_per_chars: int = 100,
    min_score: float = 1.5,
) -> dict:
    """
    处理文本，返回带注释的文本和统计信息。

    参数：
        text: 原始文本
        vocab_names: 词库名称列表
        parallel: 是否并行分词
        max_per_sentence: 每句话最多标注几个词
        max_per_chars: 每100个字符内最多标注几个词
        min_score: 最低难度分数（低于此分数的词不标注）

    返回：
        {"result": 注释后文本, "stats": {total_tokens, total_matched, total_filtered, filter_rate}}
    """
    # 1. 初始化 jieba
    custom_dict = Path(__file__).parent / "vocab" / "custom_dict.txt"
    init_jieba(str(custom_dict) if custom_dict.exists() else None)

    # 2. 加载词库 & 构建匹配器
    keyword_map = load_vocab(vocab_names)
    matcher = Matcher(keyword_map)

    # 3. 按段落处理
    paragraphs = text.split("\n")
    non_empty = [p for p in paragraphs if p.strip()]

    # 分词
    if parallel:
        all_tokens = segment_parallel(non_empty)
    else:
        all_tokens = [segment(p) for p in non_empty]

    # 匹配 → 评分 → 密度过滤 → 注释
    annotated_map = {}
    total_matched = 0
    total_filtered = 0
    total_tokens = 0

    for para, tokens in zip(non_empty, all_tokens):
        total_tokens += len(tokens)

        # 匹配（含评分）
        matches = matcher.match(tokens)
        total_matched += len(matches)

        # 密度过滤
        filtered = filter_by_density(
            para, matches,
            max_per_sentence=max_per_sentence,
            max_per_chars=max_per_chars,
            min_score=min_score,
        )
        total_filtered += len(filtered)

        # 注释
        annotated_map[para] = annotate(para, filtered)

    # 重组段落（保留空行）
    result_parts = []
    for para in paragraphs:
        if para.strip():
            result_parts.append(annotated_map.get(para, para))
        else:
            result_parts.append("")

    result = "\n".join(result_parts)

    return {
        "result": result,
        "stats": {
            "total_tokens": total_tokens,
            "total_matched": total_matched,
            "total_filtered": total_filtered,
            "filter_rate": round((1 - total_filtered / max(total_matched, 1)) * 100, 1),
        },
    }


def process_novel(
    input_file: str,
    vocab_names: list[str],
    output_file: str | None = None,
    parallel: bool = False,
    max_per_sentence: int = 3,
    max_per_chars: int = 100,
    min_score: float = 1.5,
) -> str:
    """
    处理小说文件，返回带注释的文本。

    参数：
        input_file: 输入文件名（在 data/ 目录下）
        vocab_names: 词库名称列表
        output_file: 输出文件名（默认自动生成）
        parallel: 是否并行分词
        max_per_sentence: 每句话最多标注几个词
        max_per_chars: 每100个字符内最多标注几个词
        min_score: 最低难度分数（低于此分数的词不标注）
    """
    # 读取原文
    input_path = DATA_DIR / input_file
    text = input_path.read_text(encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"输入文件: {input_path}")
    print(f"原文长度: {len(text)} 字符 ({len(text)/1024:.0f} KB)")
    print(f"选用词库: {', '.join(vocab_names)}")
    print(f"并行模式: {'开启' if parallel else '关闭'}")
    print(f"密度控制: 每句≤{max_per_sentence}, 每{max_per_chars}字≤{max_per_chars//25}, 最低分≥{min_score}")
    print(f"{'='*60}\n")

    # 处理
    output = process_text(
        text=text,
        vocab_names=vocab_names,
        parallel=parallel,
        max_per_sentence=max_per_sentence,
        max_per_chars=max_per_chars,
        min_score=min_score,
    )
    result = output["result"]
    stats = output["stats"]

    # 输出文件
    if output_file is None:
        stem = Path(input_file).stem
        output_file = f"annotated_{stem}.txt"

    output_path = OUTPUT_DIR / output_file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result, encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"输出文件: {output_path}")
    print(f"输出长度: {len(result)} 字符")
    print(f"总词数: {stats['total_tokens']}")
    print(f"匹配命中: {stats['total_matched']} → 密度过滤后: {stats['total_filtered']}")
    print(f"过滤率: {stats['filter_rate']}%")
    print(f"{'='*60}\n")

    return result


# ── 入口 ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # 支持命令行参数
    input_file = sys.argv[1] if len(sys.argv) > 1 else "sample.txt"
    parallel = "--parallel" in sys.argv

    # 密度参数
    max_per_sentence = 3
    max_per_chars = 100
    min_score = 1.5

    for arg in sys.argv:
        if arg.startswith("--max-sentence="):
            max_per_sentence = int(arg.split("=")[1])
        elif arg.startswith("--max-chars="):
            max_per_chars = int(arg.split("=")[1])
        elif arg.startswith("--min-score="):
            min_score = float(arg.split("=")[1])

    result = process_novel(
        input_file=input_file,
        vocab_names=["cet4", "cet6", "kaoyan"],
        parallel=parallel,
        max_per_sentence=max_per_sentence,
        max_per_chars=max_per_chars,
        min_score=min_score,
    )

    print("─── 注释结果预览（前1000字）───\n")
    print(result[:1000])
    if len(result) > 1000:
        print(f"\n... (共 {len(result)} 字符)")
