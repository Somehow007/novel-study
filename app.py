"""
小说英语词汇填充工具 — Web API

FastAPI 应用入口，提供文件上传、注释处理、结果下载等接口。
"""

import asyncio
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from main import process_text
from vocab.loader import get_available_vocabs

app = FastAPI(title="Novel Study", description="小说英语词汇填充工具")

# 并发控制：保护 2 核 2G 服务器
_semaphore = asyncio.Semaphore(2)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


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
    # 校验文件类型
    if not file.filename or not file.filename.endswith(".txt"):
        raise HTTPException(400, "仅支持 .txt 文件")

    # 读取文件内容
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"文件大小超过限制（最大 {MAX_FILE_SIZE // 1024 // 1024}MB）")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "文件编码不是 UTF-8，请使用 UTF-8 编码的 txt 文件")

    if not text.strip():
        raise HTTPException(400, "文件内容为空")

    # 解析词库
    vocab_names = [v.strip() for v in vocab.split(",") if v.strip()]
    available = set(get_available_vocabs().keys())
    invalid = [v for v in vocab_names if v not in available]
    if invalid:
        raise HTTPException(400, f"未知词库: {', '.join(invalid)}")

    # 处理（带并发控制）
    async with _semaphore:
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(
            None,
            lambda: process_text(
                text=text,
                vocab_names=vocab_names,
                parallel=len(text) > 100_000,
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


# 静态文件挂载（放最后，避免覆盖 API 路由）
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
