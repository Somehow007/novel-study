# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — ns CLI 打包配置

使用 --onedir 模式（非 --onefile），启动速度快，无需每次解压。

构建：
    pyinstaller ns.spec

产物：dist/ns/ 目录（内含可执行文件和依赖）
打包分发：cd dist && tar czf ns-macos-arm64.tar.gz ns/
"""

import os

block_cipher = None
ROOT = os.path.abspath(SPECPATH)

# ── 数据文件 ─────────────────────────────────────────────────────

import jieba
JIEBA_DIR = os.path.dirname(jieba.__file__)

datas = [
    (os.path.join(JIEBA_DIR, "dict.txt"), "jieba"),
    (os.path.join(ROOT, "vocab", "data"), os.path.join("vocab", "data")),
]

# ── 隐藏导入 ─────────────────────────────────────────────────────

hiddenimports = [
    "cloudscraper",
    "cloudscraper.captcha",
    "cloudscraper.exceptions",
    "js2py",
    "curl_cffi",
    "curl_cffi.requests",
    "jieba",
    "jieba.posseg",
]

# ── 排除模块 ─────────────────────────────────────────────────────

excludes = [
    "app", "fastapi", "uvicorn", "starlette", "pydantic",
    "httpcore", "httpx", "anyio",
    "pytest", "unittest",
    "tkinter", "matplotlib",
    "numpy", "scipy", "pandas",
]

# ── 分析 ─────────────────────────────────────────────────────────

a = Analysis(
    [os.path.join(ROOT, "cli.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── onedir 模式：不解压，直接运行 ─────────────────────────────────

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ns",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ns",
)
