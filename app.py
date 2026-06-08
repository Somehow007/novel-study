"""
小说英语词汇填充工具 — Web API

FastAPI 应用入口，提供文件上传、注释处理、小说爬取等接口，
支持 SSE 实时进度推送。
"""

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import StreamingResponse

from core.segmenter import init_jieba
from main import process_text
from vocab.loader import get_available_vocabs, load_vocab

# scripts/ 目录加入 sys.path 以便导入 fetch_novel
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from fetch_novel import AntiCrawlDetected, fetch_novel, get_max_threads

app = FastAPI(title="Novel Study", description="小说英语词汇填充工具")

# 并发控制：保护 2 核 2G 服务器
_semaphore = asyncio.Semaphore(2)


@app.on_event("startup")
async def _warmup():
    """后台预加载 jieba 模型 + 词库，避免首次请求卡顿。"""
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_tasks()
    loop = asyncio.get_event_loop()

    def _load():
        init_jieba()
        load_vocab(["cet4", "cet6", "kaoyan"])

    loop.run_in_executor(None, _load)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# ── 注释任务存储 ──────────────────────────────────────────────────
TASKS_DIR = Path(__file__).parent / "output" / "tasks"
TASK_EXPIRY = 24 * 3600  # 24 小时

_tasks: dict[str, dict] = {}  # task_id → {status, progress, total, result_file, error, filename, created_at}


def _cleanup_tasks():
    """清理过期的任务文件和内存记录。"""
    now = time.time()
    expired = [tid for tid, t in _tasks.items() if now - t["created_at"] > TASK_EXPIRY]
    for tid in expired:
        t = _tasks.pop(tid, {})
        p = t.get("result_file")
        if p and Path(p).exists():
            Path(p).unlink(missing_ok=True)
    # 也清理磁盘上无记录的孤立文件
    if TASKS_DIR.exists():
        for f in TASKS_DIR.iterdir():
            if f.is_file() and f.stat().st_mtime < now - TASK_EXPIRY:
                f.unlink(missing_ok=True)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/system/info")
async def system_info():
    """返回系统信息，供前端动态调整参数范围。"""
    return {"max_threads": get_max_threads()}


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
    """提交注释任务，返回 task_id 供轮询。"""
    _cleanup_tasks()

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

    task_id = uuid.uuid4().hex[:12]
    result_file = TASKS_DIR / f"{task_id}.txt"
    _tasks[task_id] = {
        "status": "running",
        "progress": 0,
        "total": 0,
        "stage": "init",
        "result_file": str(result_file),
        "filename": file.filename,
        "error": None,
        "created_at": time.time(),
    }

    loop = asyncio.get_event_loop()

    def _run():
        try:
            def _progress_cb(done, total, stage):
                _tasks[task_id]["progress"] = done
                _tasks[task_id]["total"] = total
                _tasks[task_id]["stage"] = stage

            result = process_text(
                text=text,
                vocab_names=vocab_names,
                parallel=True,
                max_per_sentence=max_per_sentence,
                max_per_chars=max_per_chars,
                min_score=min_score,
                progress_callback=_progress_cb,
            )
            result_file.write_text(result["result"], encoding="utf-8")
            _tasks[task_id]["status"] = "complete"
            _tasks[task_id]["stats"] = result["stats"]
        except Exception as e:
            _tasks[task_id]["status"] = "error"
            _tasks[task_id]["error"] = str(e)

    loop.run_in_executor(None, _run)
    return JSONResponse({"task_id": task_id})


@app.get("/api/annotate/status/{task_id}")
async def annotate_status(task_id: str):
    """查询注释任务状态。"""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在或已过期")
    resp = {
        "status": task["status"],
        "progress": task["progress"],
        "total": task["total"],
        "stage": task["stage"],
        "filename": task["filename"],
    }
    if task["status"] == "complete":
        resp["stats"] = task["stats"]
    elif task["status"] == "error":
        resp["error"] = task["error"]
    return JSONResponse(resp)


@app.get("/api/annotate/result/{task_id}")
async def annotate_result(task_id: str):
    """下载注释结果文件。"""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在或已过期")
    if task["status"] != "complete":
        raise HTTPException(400, f"任务尚未完成（当前状态: {task['status']}）")
    result_file = Path(task["result_file"])
    if not result_file.exists():
        raise HTTPException(404, "结果文件不存在")
    filename = (task["filename"] or "result").replace(".txt", "_annotated.txt")
    return FileResponse(result_file, filename=filename, media_type="text/plain")

@app.get("/api/fetch/stream")
async def fetch_stream(
    url: str = Query(..., description="小说目录页 URL"),
    start: int = Query(None, ge=1, description="起始章节"),
    end: int = Query(None, ge=1, description="结束章节"),
    delay: float = Query(0.5, ge=0.1, le=10, description="请求间隔(秒)"),
    threads: int = Query(3, ge=1, description="并发线程数"),
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
        except BaseException as e:
            progress_cb(0, 0, "error", {"message": f"内部错误: {type(e).__name__}: {e}"})

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


# ── 下载爬取好的文件 ──────────────────────────────────────────────

@app.get("/api/download")
async def download_file(path: str = Query(..., description="文件路径")):
    """下载爬取结果文件。"""
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "文件不存在")
    # 安全检查：只允许 data/ 或 output/ 目录下的文件
    base = Path(__file__).parent
    try:
        resolved = file_path.resolve()
        resolved.relative_to((base / "data").resolve())
    except ValueError:
        try:
            resolved.relative_to((base / "output").resolve())
        except ValueError:
            raise HTTPException(403, "不允许访问该路径")
    return FileResponse(file_path, filename=file_path.name, media_type="text/plain")


# 静态文件挂载（放最后，避免覆盖 API 路由）
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
