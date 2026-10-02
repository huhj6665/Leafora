"""统一响应结构 Schema.

所有接口返回统一格式 {code, message, data}。
"""
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应模型.

    code:    0 表示成功，非 0 表示业务错误码
    message: 提示信息
    data:    业务数据
    """

    code: int = 0
    message: str = "success"
    data: Optional[T] = None
