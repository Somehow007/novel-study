#!/usr/bin/env python3
"""
ns — Novel Study CLI

用法：
    ns fetch <URL> [options]          爬取小说
    ns annotate <file> [options]      注释文本
    ns vocab list                     查看可用词库
    ns config show                    查看当前配置
    ns config set <key> <value>       修改配置
    ns config reset                   重置为默认配置
    ns serve [--port 8000]            启动 Web 服务
    ns update                         自更新
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

import config as cfg


# ── 颜色输出 ────────────────────────────────────────────────────

def _supports_color():
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_COLOR = _supports_color()

def _c(text, code):
    return f"\033[{code}m{text}\033[0m" if _COLOR else text

def bold(t): return _c(t, "1")
def green(t): return _c(t, "32")
def yellow(t): return _c(t, "33")
def red(t): return _c(t, "31")
def dim(t): return _c(t, "2")


# ── 子命令：fetch ───────────────────────────────────────────────

def cmd_fetch(args):
    """爬取小说。"""
    from scripts.fetch_novel import fetch_novel, get_max_threads

    threads = args.threads or cfg.get("default_threads")
    delay = args.delay or cfg.get("default_delay")
    batch = args.batch or cfg.get("default_batch")
    proxy = args.proxy or cfg.get("proxy")

    # 线程数上限校验
    max_t = get_max_threads()
    if threads > max_t:
        print(yellow(f"[提示] 线程数 {threads} 超过推荐上限 {max_t}，已自动调整"))
        threads = max_t

    try:
        fetch_novel(
            url=args.url,
            output_dir=args.output_dir or cfg.get("output_dir"),
            start=args.start,
            end=args.end,
            delay=delay,
            threads=threads,
            batch=batch,
            resume=args.resume,
            encoding=args.encoding,
            proxy=proxy,
        )
    except KeyboardInterrupt:
        print(yellow("\n[中断] 用户取消"))
        sys.exit(130)
    except Exception as e:
        print(red(f"\n[错误] {e}"))
        sys.exit(1)


# ── 子命令：annotate ────────────────────────────────────────────

def cmd_annotate(args):
    """注释文本。"""
    from main import process_novel

    input_file = args.file
    if not Path(input_file).exists():
        print(red(f"[错误] 文件不存在: {input_file}"))
        sys.exit(1)

    vocab = args.vocab.split(",") if args.vocab else cfg.get("default_vocab")
    min_score = args.min_score if args.min_score is not None else cfg.get("default_min_score")
    max_sentence = args.max_sentence or cfg.get("default_max_per_sentence")
    max_chars = args.max_chars or cfg.get("default_max_per_chars")

    try:
        result = process_novel(
            input_file=input_file,
            vocab_names=vocab,
            parallel=args.parallel,
            max_per_sentence=max_sentence,
            max_per_chars=max_chars,
            min_score=min_score,
        )
        if not args.quiet:
            preview = result[:1000]
            print(preview)
            if len(result) > 1000:
                print(dim(f"\n... (共 {len(result)} 字符)"))
    except KeyboardInterrupt:
        print(yellow("\n[中断] 用户取消"))
        sys.exit(130)
    except Exception as e:
        print(red(f"\n[错误] {e}"))
        sys.exit(1)


# ── 子命令：vocab ───────────────────────────────────────────────

def cmd_vocab(args):
    """词库管理。"""
    from vocab.loader import get_available_vocabs

    vocabs = get_available_vocabs()
    print(bold("可用词库：\n"))
    for name, info in vocabs.items():
        count = info.get("count", "?")
        desc = info.get("description", "")
        print(f"  {green(name):20s} {count:>5} 条  {dim(desc)}")
    print()


# ── 子命令：config ──────────────────────────────────────────────

def cmd_config(args):
    """配置管理。"""
    if args.config_action == "show":
        print(bold("当前配置：\n"))
        print(cfg.show())
        print(f"\n  配置文件: {cfg.CONFIG_FILE}")

    elif args.config_action == "set":
        if not args.key or args.value is None:
            print(red("[错误] 用法: ns config set <key> <value>"))
            sys.exit(1)
        # value 可能被 argparse 合并成一个字符串
        value = " ".join(args.value) if isinstance(args.value, list) else args.value
        try:
            cfg.set_value(args.key, value)
            print(green(f"[OK] {args.key} = {value}"))
        except ValueError as e:
            print(red(f"[错误] {e}"))
            sys.exit(1)

    elif args.config_action == "reset":
        cfg.reset()
        print(green("[OK] 配置已重置为默认值"))


# ── 子命令：serve ───────────────────────────────────────────────

def cmd_serve(args):
    """启动 Web 服务。"""
    port = args.port or 8000
    host = args.host or "0.0.0.0"
    print(bold(f"启动 Web 服务: http://{host}:{port}"))
    print(dim("按 Ctrl+C 停止\n"))
    try:
        subprocess.run(
            [sys.executable, "-m", "uvicorn", "app:app",
             "--host", host, "--port", str(port)],
            cwd=str(PROJECT_ROOT),
        )
    except KeyboardInterrupt:
        print(yellow("\n[停止] Web 服务已关闭"))


# ── 子命令：update ──────────────────────────────────────────────

def cmd_update(args):
    """自更新。"""
    print(bold("正在更新..."))
    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=str(PROJECT_ROOT),
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(red(f"[错误] git pull 失败:\n{result.stderr}"))
            sys.exit(1)
        print(result.stdout.strip())

        # 安装依赖
        print(dim("安装依赖..."))
        if (PROJECT_ROOT / "uv.lock").exists():
            subprocess.run(["uv", "sync"], cwd=str(PROJECT_ROOT))
        else:
            subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."],
                           cwd=str(PROJECT_ROOT))
        print(green("[OK] 更新完成"))
    except Exception as e:
        print(red(f"[错误] {e}"))
        sys.exit(1)


# ── 主入口 ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="ns",
        description="ns — Novel Study 小说英语词汇注释工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=dim("""示例:
  ns fetch https://example.com/book/123/          爬取小说
  ns fetch <URL> --threads 5 --resume             多线程 + 断点续传
  ns annotate novel.txt                           注释小说
  ns annotate novel.txt --vocab cet6,kaoyan       指定词库
  ns vocab list                                   查看词库
  ns config set default_threads 8                 修改默认线程数
  ns serve                                        启动 Web 服务
"""),
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # fetch
    p_fetch = subparsers.add_parser("fetch", help="爬取小说")
    p_fetch.add_argument("url", help="小说目录页 URL")
    p_fetch.add_argument("-o", "--output-dir", help="输出目录")
    p_fetch.add_argument("--start", type=int, help="起始章节")
    p_fetch.add_argument("--end", type=int, help="结束章节")
    p_fetch.add_argument("--threads", type=int, help=f"并发线程数（默认 {cfg.get('default_threads')}）")
    p_fetch.add_argument("--delay", type=float, help=f"请求间隔秒数（默认 {cfg.get('default_delay')}）")
    p_fetch.add_argument("--batch", type=int, help=f"每多少章写入一次（默认 {cfg.get('default_batch')}）")
    p_fetch.add_argument("--resume", action="store_true", help="断点续传")
    p_fetch.add_argument("--encoding", help="强制编码（如 gbk）")
    p_fetch.add_argument("--proxy", help="HTTP 代理")
    p_fetch.set_defaults(func=cmd_fetch)

    # annotate
    p_anno = subparsers.add_parser("annotate", help="注释文本")
    p_anno.add_argument("file", help="要注释的 .txt 文件")
    p_anno.add_argument("--vocab", help="词库，逗号分隔（默认 cet4,cet6,kaoyan）")
    p_anno.add_argument("--min-score", type=float, help="最低难度分数")
    p_anno.add_argument("--max-sentence", type=int, help="每句最多标注词数")
    p_anno.add_argument("--max-chars", type=int, help="字符窗口大小")
    p_anno.add_argument("--parallel", action="store_true", help="强制并行模式")
    p_anno.add_argument("-q", "--quiet", action="store_true", help="静默模式，不输出预览")
    p_anno.set_defaults(func=cmd_annotate)

    # vocab
    p_vocab = subparsers.add_parser("vocab", help="词库管理")
    p_vocab.add_argument("vocab_action", nargs="?", default="list",
                         choices=["list"], help="操作（目前仅支持 list）")
    p_vocab.set_defaults(func=cmd_vocab)

    # config
    p_cfg = subparsers.add_parser("config", help="配置管理")
    p_cfg.add_argument("config_action", choices=["show", "set", "reset"],
                       help="操作: show | set | reset")
    p_cfg.add_argument("key", nargs="?", help="配置项名称")
    p_cfg.add_argument("value", nargs="*", help="配置值")
    p_cfg.set_defaults(func=cmd_config)

    # serve
    p_serve = subparsers.add_parser("serve", help="启动 Web 服务")
    p_serve.add_argument("--port", type=int, help="端口（默认 8000）")
    p_serve.add_argument("--host", help="监听地址（默认 0.0.0.0）")
    p_serve.set_defaults(func=cmd_serve)

    # update
    p_update = subparsers.add_parser("update", help="自更新")
    p_update.set_defaults(func=cmd_update)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
