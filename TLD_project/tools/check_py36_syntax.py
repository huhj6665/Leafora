# -*- coding: utf-8 -*-
"""在新版本 Python 上按 3.6 语法级别检查全部项目 Python 文件。"""

import ast
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    checked = 0
    for base, directories, files in os.walk(ROOT):
        directories[:] = [name for name in directories if name not in ("__pycache__", "runtime", ".idea")]
        for filename in files:
            if not filename.endswith(".py"):
                continue
            path = os.path.join(base, filename)
            with open(path, "r", encoding="utf-8") as handle:
                source = handle.read()
            if sys.version_info[:2] >= (3, 8):
                ast.parse(source, filename=path, feature_version=(3, 6))
            else:
                compile(source, path, "exec")
            checked += 1
    print("Python 3.6 syntax OK: {} files".format(checked))
    return 0


if __name__ == "__main__":
    sys.exit(main())
