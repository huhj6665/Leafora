"""统一响应构建工具.

所有接口统一返回结构：
    {
        "code": 0,       # 0 表示成功，非 0 表示业务错误码
        "message": "success",
        "data": {}       # 业务数据
    }
"""
from typing import Any


def ok(data: Any = None, message: str = "success") -> dict:
    """构造成功响应."""
    return {"code": 0, "message": message, "data": data}


def fail(code: int = 1, message: str = "error", data: Any = None) -> dict:
    """构造失败响应."""
    return {"code": code, "message": message, "data": data}
