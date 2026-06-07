"""
小说英语词汇填充工具 — Web API

FastAPI 应用入口，提供文件上传、注释处理、小说爬取等接口，
支持 SSE 实时进度推送。
"""

import asyncio
import json
import sys
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import StreamingResponse

from core.segmenter import init_jieba
from main import process_text
from vocab.loader import get_available_vocabs, load_vocab

# scripts/ 目录加入 sys.path 以便导入 fetch_novel
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from fetch_novel import AntiCrawlDetected, fetch_novel

app = FastAPI(title="Novel Study", description="小说英语词汇填充工具")

# 并发控制：保护 2 核 2G 服务器
_semaphore = asyncio.Semaphore(2)


@app.on_event("startup")
async def _warmup():
    """后台预加载 jieba 模型 + 词库，避免首次请求卡顿。"""
    loop = asyncio.get_event_loop()

    def _load():
        custom_dict = Path(__file__).parent / "vocab" / "custom_dict.txt"
        init_jieba(str(custom_dict) if custom_dict.exists() else None)
        load_vocab(["cet4", "cet6", "kaoyan"])

    loop.run_in_executor(None, _load)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/vocabs")
async def vocabs():
    return get_available_vocabs()


@app.post("/api/annotate")
async def annotate(
    file: UploadFile = File(...),
    vocab: str = Form("cet4,cet6,kaoyan"),
    max_per_sentence: int = Form(3),
    max_per_chars: int = Form(100),
    min_score: float = Form(1.5),
):
    """同步注释接口（兼容旧版，无进度推送）。"""
    if not file.filename or not file.filename.endswith(".txt"):
        raise HTTPException(400, "仅支持 .txt 文件")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"文件大小超过限制（最大 {MAX_FILE_SIZE // 1024 // 1024}MB）")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "文件编码不是 UTF-8，请使用 UTF-8 编码的 txt 文件")

    if not text.strip():
        raise HTTPException(400, "文件内容为空")

    vocab_names = [v.strip() for v in vocab.split(",") if v.strip()]
    available = set(get_available_vocabs().keys())
    invalid = [v for v in vocab_names if v not in available]
    if invalid:
        raise HTTPException(400, f"未知词库: {', '.join(invalid)}")

    async with _semaphore:
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(
            None,
            lambda: process_text(
                text=text,
                vocab_names=vocab_names,
                parallel=True,
                max_per_sentence=max_per_sentence,
                max_per_chars=max_per_chars,
                min_score=min_score,
            ),
        )

    return JSONResponse({
        "result": output["result"],
        "stats": output["stats"],
        "filename": file.filename,
    })


# ── SSE 实时进度 ──────────────────────────────────────────────────

@app.get("/api/fetch/stream")
async def fetch_stream(
    url: str = Query(..., description="小说目录页 URL"),
    start: int = Query(None, ge=1, description="起始章节"),
    end: int = Query(None, ge=1, description="结束章节"),
    delay: float = Query(0.5, ge=0.1, le=10, description="请求间隔(秒)"),
    threads: int = Query(3, ge=1, le=10, description="并发线程数"),
    encoding: str = Query(None, description="强制编码"),
):
    """SSE 流式爬取小说，实时推送进度。"""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL 需以 http:// 或 https:// 开头")

    queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    async def run_crawl():
        def progress_cb(done, total, stage, info=None):
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"done": done, "total": total, "stage": stage, **(info or {})},
            )

        try:
            async with _semaphore:
                await loop.run_in_executor(
                    None,
                    lambda: fetch_novel(
                        url=url, start=start, end=end,
                        delay=delay, threads=threads,
                        encoding=encoding, progress_callback=progress_cb,
                    ),
                )
        except AntiCrawlDetected as e:
            progress_cb(0, 0, "error", {"message": f"{e.reason}\n{e.details}"})
        except Exception as e:
            progress_cb(0, 0, "error", {"message": str(e)})

    task = asyncio.create_task(run_crawl())

    async def event_stream():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    # 保持连接活跃，防止代理/浏览器超时断开
                    yield ": keepalive\n\n"
                    continue
                stage = data.get("stage", "progress")
                yield f"event: {stage}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                if stage in ("complete", "error"):
                    break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/annotate/stream")
async def annotate_stream(
    file: UploadFile = File(...),
    vocab: str = Form("cet4,cet6,kaoyan"),
    max_per_sentence: int = Form(3),
    max_per_chars: int = Form(100),
    min_score: float = Form(1.5),
):
    """SSE 流式注释，实时推送分词/注释进度。"""
    if not file.filename or not file.filename.endswith(".txt"):
        raise HTTPException(400, "仅支持 .txt 文件")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"文件大小超过限制（最大 {MAX_FILE_SIZE // 1024 // 1024}MB）")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "文件编码不是 UTF-8，请使用 UTF-8 编码的 txt 文件")

    if not text.strip():
        raise HTTPException(400, "文件内容为空")

    vocab_names = [v.strip() for v in vocab.split(",") if v.strip()]
    available = set(get_available_vocabs().keys())
    invalid = [v for v in vocab_names if v not in available]
    if invalid:
        raise HTTPException(400, f"未知词库: {', '.join(invalid)}")

    queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    async def run_annotate():
        def progress_cb(done, total, stage):
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"done": done, "total": total, "stage": stage},
            )

        try:
            async with _semaphore:
                result = await loop.run_in_executor(
                    None,
                    lambda: process_text(
                        text=text,
                        vocab_names=vocab_names,
                        parallel=True,
                        max_per_sentence=max_per_sentence,
                        max_per_chars=max_per_chars,
                        min_score=min_score,
                        progress_callback=progress_cb,
                    ),
                )
            await queue.put({"stage": "complete", **result})
        except Exception as e:
            await queue.put({"stage": "error", "message": str(e)})

    task = asyncio.create_task(run_annotate())

    async def event_stream():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                stage = data.get("stage", "progress")
                yield f"event: {stage}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                if stage in ("complete", "error"):
                    break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 下载爬取好的文件 ──────────────────────────────────────────────

@app.get("/api/download")
async def download_file(path: str = Query(..., description="文件路径")):
    """下载爬取结果文件。"""
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "文件不存在")
    # 安全检查：只允许 data/ 目录下的文件
    data_dir = Path(__file__).parent / "data"
    try:
        file_path.resolve().relative_to(data_dir.resolve())
    except ValueError:
        raise HTTPException(403, "不允许访问该路径")
    return FileResponse(file_path, filename=file_path.name, media_type="text/plain")


# 静态文件挂载（放最后，避免覆盖 API 路由）
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
