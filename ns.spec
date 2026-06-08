# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — ns CLI 打包配置

只打包命令行相关代码，不包含 Web 服务（app.py、fastapi、uvicorn）。

构建：
    pyinstaller ns.spec

产物：dist/ns（单文件可执行）
"""

import os

block_cipher = None
ROOT = os.path.abspath(SPECPATH)

# ── 数据文件 ─────────────────────────────────────────────────────

import jieba
JIEBA_DIR = os.path.dirname(jieba.__file__)

datas = [
    # jieba 主词典
    (os.path.join(JIEBA_DIR, "dict.txt"), "jieba"),
    # 词库数据
    (os.path.join(ROOT, "vocab", "data"), os.path.join("vocab", "data")),
]

# ── 隐藏导入 ─────────────────────────────────────────────────────

hiddenimports = [
    # cloudscraper 动态导入
    "cloudscraper",
    "cloudscraper.captcha",
    "cloudscraper.exceptions",
    "js2py",
    # curl_cffi
    "curl_cffi",
    "curl_cffi.requests",
    # jieba
    "jieba",
    "jieba.posseg",
]

# ── 排除模块（减小体积，不打包 Web 相关） ─────────────────────────

excludes = [
    # Web 服务（CLI 不需要）
    "app",
    "fastapi",
    "uvicorn",
    "starlette",
    "pydantic",
    "httpcore",
    "httpx",
    "anyio",
    # 测试
    "pytest",
    "unittest",
    # GUI
    "tkinter",
    "matplotlib",
    # 科学计算
    "numpy",
    "scipy",
    "pandas",
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

# ── 打包为单文件 ─────────────────────────────────────────────────

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ns",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,             # 需要安装 upx：brew install upx
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
)
