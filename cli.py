#!/usr/bin/env python3
"""
ns — Novel Study CLI

用法：
    ns fetch <URL> [options]          爬取小说
    ns annotate <file> [options]      注释文本
    ns vocab list                     查看可用词库
    ns vocab info <name>              词库详情
    ns config show                    查看当前配置
    ns config get <key>               获取单个配置值
    ns config set <key> <value>       修改配置
    ns config edit                    用编辑器打开配置文件
    ns config init                    交互式初始化配置
    ns config reset                   重置为默认配置
    ns serve [--port 8000]            启动 Web 服务
    ns update                         自更新
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

VERSION = "0.2.0"

# ── 路径兼容：源码运行 vs PyInstaller 打包 ────────────────────────

def _get_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent

def _get_project_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent

BASE_DIR = _get_base_dir()
PROJECT_ROOT = _get_project_root()

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(BASE_DIR))

import config as cfg


# ── 颜色输出 ────────────────────────────────────────────────────

def _supports_color():
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

_COLOR = _supports_color()
def _c(text, code): return f"\033[{code}m{text}\033[0m" if _COLOR else text
def bold(t): return _c(t, "1")
def green(t): return _c(t, "32")
def yellow(t): return _c(t, "33")
def red(t): return _c(t, "31")
def dim(t): return _c(t, "2")
def cyan(t): return _c(t, "36")


# ── 交互式输入辅助 ──────────────────────────────────────────────

def _prompt(key: str, default, desc: str):
    """交互式提示用户输入，回车使用默认值。"""
    current = cfg.get(key) if cfg.get(key) is not None else default
    if isinstance(current, list):
        current = ",".join(current)
    hint = dim(f" [{current}]") if current else ""
    val = input(f"  {desc}{hint}: ").strip()
    return val if val else str(current) if current is not None else ""


# ── 子命令：fetch ───────────────────────────────────────────────

def cmd_fetch(args):
    """爬取小说。"""
    from scripts.fetch_novel import fetch_novel, get_max_threads

    threads = args.threads or cfg.get("default_threads")
    delay = args.delay or cfg.get("default_delay")
    batch = args.batch or cfg.get("default_batch")
    proxy = args.proxy or cfg.get("proxy")

    max_t = get_max_threads()
    if threads > max_t:
        print(yellow(f"[提示] 线程数 {threads} 超过推荐上限 {max_t}，已自动调整"))
        threads = max_t

    output_dir = args.output_dir or cfg.get("output_dir")
    if output_dir:
        output_dir = str(Path(output_dir).resolve())
    else:
        output_dir = str(Path.cwd())

    # 显示生效参数
    print(dim(f"  线程={threads}  延迟={delay}s  批量={batch}  输出={output_dir}"))
    if proxy:
        print(dim(f"  代理={proxy}"))

    try:
        fetch_novel(
            url=args.url, output_dir=output_dir,
            start=args.start, end=args.end,
            delay=delay, threads=threads, batch=batch,
            resume=args.resume, encoding=args.encoding, proxy=proxy,
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
    from main import process_text
    from core.segmenter import init_jieba
    from vocab.loader import load_vocab

    input_path = Path(args.file)
    if not input_path.exists():
        print(red(f"[错误] 文件不存在: {input_path}"))
        sys.exit(1)

    text = input_path.read_text(encoding="utf-8")
    if not text.strip():
        print(red("[错误] 文件内容为空"))
        sys.exit(1)

    vocab = args.vocab.split(",") if args.vocab else cfg.get("default_vocab")
    min_score = args.min_score if args.min_score is not None else cfg.get("default_min_score")
    max_sentence = args.max_sentence or cfg.get("default_max_per_sentence")
    max_chars = args.max_chars or cfg.get("default_max_per_chars")

    # 显示生效参数
    print(dim(f"  词库={','.join(vocab)}  最低分={min_score}  每句≤{max_sentence}  每{max_chars}字≤{max_chars//25}"))

    print(dim("初始化分词引擎和词库..."))
    init_jieba()
    load_vocab(vocab)

    stage_names = {"init": "初始化", "segment": "分词", "annotate": "注释"}
    t0 = time.time()

    def _progress(done, total, stage):
        name = stage_names.get(stage, stage)
        if total == 0:
            sys.stderr.write(f"\r[{name}] ...")
        else:
            pct = done / total * 100
            elapsed = time.time() - t0
            speed = done / elapsed if elapsed > 0 else 0
            sys.stderr.write(f"\r[{name}] {done}/{total} ({pct:.0f}%) | {speed:.0f} 段/秒")
        sys.stderr.flush()

    try:
        result = process_text(
            text=text, vocab_names=vocab, parallel=args.parallel,
            max_per_sentence=max_sentence, max_per_chars=max_chars,
            min_score=min_score, progress_callback=_progress,
        )
    except KeyboardInterrupt:
        print(yellow("\n[中断] 用户取消"))
        sys.exit(130)
    except Exception as e:
        print(red(f"\n[错误] {e}"))
        sys.exit(1)

    sys.stderr.write("\r" + " " * 60 + "\r")
    sys.stderr.flush()

    output_file = args.output or f"annotated_{input_path.stem}.txt"
    out_dir = Path(args.output_dir) if args.output_dir else Path.cwd()
    output_path = out_dir / output_file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result["result"], encoding="utf-8")

    stats = result["stats"]
    print(f"\n{'='*50}")
    print(f"  输出: {output_path}")
    print(f"  长度: {len(result['result'])} 字符")
    print(f"  词数: {stats['total_tokens']}  命中: {stats['total_matched']}  过滤后: {stats['total_filtered']}")
    print(f"  过滤率: {stats['filter_rate']}%")
    print(f"{'='*50}")


# ── 子命令：vocab ───────────────────────────────────────────────

def cmd_vocab(args):
    """词库管理。"""
    from vocab.loader import get_available_vocabs

    vocabs = get_available_vocabs()

    if args.vocab_action == "list":
        print(bold("可用词库：\n"))
        for name, info in vocabs.items():
            count = info.get("count", "?")
            desc = info.get("description", "")
            print(f"  {green(name):20s} {count:>5} 条  {dim(desc)}")
        print()

    elif args.vocab_action == "info":
        if not args.name:
            print(red("[错误] 用法: ns vocab info <词库名>"))
            print(dim(f"  可选: {', '.join(vocabs.keys())}"))
            sys.exit(1)
        name = args.name
        if name not in vocabs:
            print(red(f"[错误] 未知词库: {name}"))
            print(dim(f"  可选: {', '.join(vocabs.keys())}"))
            sys.exit(1)
        info = vocabs[name]
        print(bold(f"词库: {name}\n"))
        print(f"  条目数: {info.get('count', '?')}")
        print(f"  说明: {info.get('description', '无')}")
        print(f"  文件: {info.get('path', '未知')}")
        # 显示前 5 个示例
        entries = info.get("entries", [])
        if entries:
            print(f"\n  {dim('示例词条:')}")
            for e in entries[:5]:
                word = e.get("word", "")
                pos = e.get("pos", "")
                cn = "、".join(e.get("cn_meanings", [])[:2])
                print(f"    {cyan(word)} ({pos}) {cn}")


# ── 子命令：config ──────────────────────────────────────────────

def cmd_config(args):
    """配置管理。"""
    action = args.config_action

    if action == "show":
        print(bold("当前配置：\n"))
        print(cfg.show())
        print(f"\n  配置文件: {cfg.CONFIG_FILE}")

    elif action == "get":
        if not args.key:
            print(red("[错误] 用法: ns config get <key>"))
            sys.exit(1)
        val = cfg.get(args.key)
        if val is None:
            print(dim(f"  {args.key} = null"))
        else:
            print(f"  {args.key} = {json.dumps(val, ensure_ascii=False)}")

    elif action == "set":
        if not args.key or args.value is None:
            print(red("[错误] 用法: ns config set <key> <value>"))
            print(dim(f"  可用配置项: {', '.join(cfg.DEFAULTS.keys())}"))
            sys.exit(1)
        value = " ".join(args.value) if isinstance(args.value, list) else args.value
        try:
            cfg.set_value(args.key, value)
            print(green(f"[OK] {args.key} = {value}"))
        except ValueError as e:
            print(red(f"[错误] {e}"))
            sys.exit(1)

    elif action == "edit":
        import shutil
        cfg.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if not cfg.CONFIG_FILE.exists():
            cfg._save(dict(cfg.DEFAULTS))
            print(dim(f"已创建默认配置: {cfg.CONFIG_FILE}"))
        editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
        if not editor:
            # 尝试常见编辑器
            for e in ("vim", "nano", "vi", "code"):
                if shutil.which(e):
                    editor = e
                    break
        if not editor:
            print(red("[错误] 未找到编辑器，请设置 EDITOR 环境变量"))
            print(dim(f"  配置文件位置: {cfg.CONFIG_FILE}"))
            sys.exit(1)
        os.execlp(editor, editor, str(cfg.CONFIG_FILE))

    elif action == "init":
        print(bold("交互式配置向导\n"))
        print(dim("  回车使用默认值，输入值覆盖默认\n"))

        data = {}
        data["default_threads"] = int(_prompt("default_threads", 3, "默认爬取线程数"))
        data["default_delay"] = float(_prompt("default_delay", 0.5, "默认请求间隔（秒）"))
        data["default_batch"] = int(_prompt("default_batch", 50, "每多少章写入一次文件"))
        vocab_str = _prompt("default_vocab", "cet4,cet6,kaoyan", "默认词库（逗号分隔）")
        data["default_vocab"] = [v.strip() for v in vocab_str.split(",") if v.strip()]
        data["default_min_score"] = float(_prompt("default_min_score", 1.5, "最低难度分数"))
        data["default_max_per_sentence"] = int(_prompt("default_max_per_sentence", 3, "每句最多标注词数"))
        data["default_max_per_chars"] = int(_prompt("default_max_per_chars", 100, "字符窗口大小"))
        proxy = _prompt("proxy", "", "HTTP 代理（留空跳过）")
        data["proxy"] = proxy if proxy else None
        out_dir = _prompt("output_dir", "", "默认输出目录（留空=当前目录）")
        data["output_dir"] = out_dir if out_dir else None

        cfg._save(data)
        print(f"\n{green('[OK]')} 配置已保存到 {cfg.CONFIG_FILE}")
        print(dim("  使用 ns config show 查看"))

    elif action == "reset":
        cfg.reset()
        print(green("[OK] 配置已重置为默认值"))


# ── 子命令：serve ───────────────────────────────────────────────

def cmd_serve(args):
    """启动 Web 服务。"""
    if getattr(sys, 'frozen', False):
        print(red("[错误] 打包版不支持 serve 命令，请从源码运行 Web 服务"))
        print(dim("  git clone https://github.com/Somehow007/novel-study.git"))
        print(dim("  cd novel-study && uv sync && uv run uvicorn app:app"))
        sys.exit(1)

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
    if getattr(sys, 'frozen', False):
        print(red("[错误] 打包版不支持自动更新，请重新下载最新版本"))
        print(dim("  https://github.com/Somehow007/novel-study/releases"))
        sys.exit(1)

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
        epilog=dim(f"""示例:
  ns fetch https://example.com/book/123/          爬取小说
  ns fetch <URL> --threads 5 --resume             多线程 + 断点续传
  ns annotate novel.txt                           注释小说
  ns annotate novel.txt --vocab cet6,kaoyan       指定词库
  ns vocab list                                   查看词库
  ns vocab info cet6                              词库详情
  ns config init                                  交互式配置
  ns config set default_threads 8                 修改配置
  ns config edit                                  编辑器打开配置
  ns serve                                        启动 Web 服务

配置文件: {cfg.CONFIG_FILE}
"""),
    )
    parser.add_argument("-v", "--version", action="version", version=f"ns {VERSION}")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # ── fetch ──
    p_fetch = subparsers.add_parser("fetch", help="爬取小说",
        description="从网络小说站爬取全本内容，输出纯文本 .txt")
    p_fetch.add_argument("url", help="小说目录页 URL")
    p_fetch.add_argument("-o", "--output-dir", help="输出目录（默认当前目录）")
    p_fetch.add_argument("--start", type=int, help="起始章节（从 1 开始）")
    p_fetch.add_argument("--end", type=int, help="结束章节（包含）")
    p_fetch.add_argument("--threads", type=int, help=f"并发线程数（默认读取配置）")
    p_fetch.add_argument("--delay", type=float, help="请求间隔秒数")
    p_fetch.add_argument("--batch", type=int, help="每多少章写入一次文件")
    p_fetch.add_argument("--resume", action="store_true", help="断点续传")
    p_fetch.add_argument("--encoding", help="强制编码（如 gbk, utf-8）")
    p_fetch.add_argument("--proxy", help="HTTP 代理（如 http://127.0.0.1:7890）")
    p_fetch.set_defaults(func=cmd_fetch)

    # ── annotate ──
    p_anno = subparsers.add_parser("annotate", help="注释文本",
        description="为中文小说文本自动插入英文词汇注释")
    p_anno.add_argument("file", help="要注释的 .txt 文件")
    p_anno.add_argument("-o", "--output", help="输出文件名（默认 annotated_原文件名.txt）")
    p_anno.add_argument("--output-dir", help="输出目录（默认当前目录）")
    p_anno.add_argument("--vocab", help="词库，逗号分隔（默认读取配置）")
    p_anno.add_argument("--min-score", type=float, help="最低难度分数")
    p_anno.add_argument("--max-sentence", type=int, help="每句最多标注词数")
    p_anno.add_argument("--max-chars", type=int, help="字符窗口大小")
    p_anno.add_argument("--parallel", action="store_true", help="强制并行模式")
    p_anno.add_argument("-q", "--quiet", action="store_true", help="静默模式")
    p_anno.set_defaults(func=cmd_annotate)

    # ── vocab ──
    p_vocab = subparsers.add_parser("vocab", help="词库管理",
        description="查看可用词库及详情")
    p_vocab.add_argument("vocab_action", nargs="?", default="list",
                         choices=["list", "info"], help="操作: list | info")
    p_vocab.add_argument("name", nargs="?", help="词库名称（info 时必填）")
    p_vocab.set_defaults(func=cmd_vocab)

    # ── config ──
    p_cfg = subparsers.add_parser("config", help="配置管理",
        description="查看、修改、初始化配置")
    p_cfg.add_argument("config_action",
                       choices=["show", "get", "set", "edit", "init", "reset"],
                       help="show | get | set | edit | init | reset")
    p_cfg.add_argument("key", nargs="?", help="配置项名称")
    p_cfg.add_argument("value", nargs="*", help="配置值")
    p_cfg.set_defaults(func=cmd_config)

    # ── serve ──
    p_serve = subparsers.add_parser("serve", help="启动 Web 服务",
        description="启动本地 Web 界面（源码模式）")
    p_serve.add_argument("--port", type=int, help="端口（默认 8000）")
    p_serve.add_argument("--host", help="监听地址（默认 0.0.0.0）")
    p_serve.set_defaults(func=cmd_serve)

    # ── update ──
    p_update = subparsers.add_parser("update", help="自更新",
        description="从 git 拉取最新代码并更新依赖（源码模式）")
    p_update.set_defaults(func=cmd_update)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
