"""
词库格式校验脚本

使用 JSON Schema 校验词库数据格式。
"""

import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("需要安装 jsonschema: uv add jsonschema")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).parent.parent
SCHEMA_PATH = PROJECT_ROOT / "vocab" / "schema.json"
DATA_DIR = PROJECT_ROOT / "vocab" / "data"


def validate_all():
    """校验所有词库文件。"""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)

    errors_total = 0

    for json_file in sorted(DATA_DIR.glob("*.json")):
        if json_file.name == "index.json":
            continue

        print(f"\n校验: {json_file.name}")
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)

        errors = []
        for i, entry in enumerate(data):
            try:
                jsonschema.validate(entry, schema["items"])
            except jsonschema.ValidationError as e:
                errors.append((i, entry.get("word", "?"), str(e.message)[:80]))

        if errors:
            print(f"  ✗ {len(errors)} 个错误")
            for idx, word, msg in errors[:5]:
                print(f"    [{idx}] {word}: {msg}")
            if len(errors) > 5:
                print(f"    ... 还有 {len(errors)-5} 个错误")
            errors_total += len(errors)
        else:
            print(f"  ✓ 通过 ({len(data)} 条)")

    print(f"\n{'='*40}")
    if errors_total:
        print(f"校验完成: {errors_total} 个错误")
        return False
    else:
        print("校验完成: 全部通过")
        return True


if __name__ == "__main__":
    ok = validate_all()
    sys.exit(0 if ok else 1)
