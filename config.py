"""
配置管理模块

配置文件路径：~/.novel-study/config.json
"""

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".novel-study"
CONFIG_FILE = CONFIG_DIR / "config.json"

# 默认配置
DEFAULTS = {
    "default_threads": 3,
    "default_delay": 0.5,
    "default_batch": 50,
    "default_vocab": ["cet4", "cet6", "kaoyan"],
    "default_min_score": 1.5,
    "default_max_per_sentence": 3,
    "default_max_per_chars": 100,
    "proxy": None,
    "output_dir": None,
}

# 配置项说明（用于 config show 展示）
DESCRIPTIONS = {
    "default_threads": "默认并发下载线程数",
    "default_delay": "默认请求间隔（秒）",
    "default_batch": "每多少章写入一次文件",
    "default_vocab": "默认词库列表",
    "default_min_score": "最低难度分数",
    "default_max_per_sentence": "每句最多标注词数",
    "default_max_per_chars": "每 N 字符内标注密度限制",
    "proxy": "HTTP 代理地址",
    "output_dir": "默认输出目录",
}


def _load() -> dict:
    """加载配置文件，不存在则返回空字典。"""
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict):
    """保存配置文件。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def get(key: str):
    """获取配置值，优先用户配置，回退默认值。"""
    data = _load()
    if key in data:
        return data[key]
    return DEFAULTS.get(key)


def get_all() -> dict:
    """获取完整配置（默认值 + 用户覆盖）。"""
    merged = dict(DEFAULTS)
    merged.update(_load())
    return merged


def set_value(key: str, value):
    """设置配置值。"""
    if key not in DEFAULTS:
        raise ValueError(f"未知配置项: {key}（可选: {', '.join(DEFAULTS)}）")
    # 类型校验
    expected = type(DEFAULTS[key])
    if expected is list:
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]
        if not isinstance(value, list):
            raise ValueError(f"配置项 {key} 需要列表类型")
    elif expected is type(None):
        pass  # proxy 等可为 null
    else:
        try:
            value = expected(value)
        except (ValueError, TypeError):
            raise ValueError(f"配置项 {key} 需要 {expected.__name__} 类型")
    data = _load()
    data[key] = value
    _save(data)


def show() -> str:
    """格式化展示当前配置。"""
    cfg = get_all()
    lines = []
    for key, default in DEFAULTS.items():
        val = cfg.get(key, default)
        desc = DESCRIPTIONS.get(key, "")
        user_overridden = key in _load()
        marker = " *" if user_overridden else ""
        lines.append(f"  {key} = {json.dumps(val, ensure_ascii=False)}{marker}")
        if desc:
            lines.append(f"    # {desc}")
    lines.append("")
    lines.append("  * = 用户自定义（未标记的为默认值）")
    return "\n".join(lines)


def reset():
    """重置为默认配置（删除配置文件）。"""
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
