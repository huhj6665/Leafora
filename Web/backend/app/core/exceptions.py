"""业务异常定义.

统一业务异常携带业务错误码 code 与 HTTP 状态码 status_code，
由 main.py 中的全局异常处理器转换为统一响应格式 {code, message, data}。
"""
from typing import Any


class BusinessError(Exception):
    """业务异常基类.

    参数:
        message:     面向用户的错误描述
        code:        业务错误码（默认 1，与统一响应中的 code 字段对应）
        status_code: HTTP 状态码
        data:        可选的附加数据
    """

    def __init__(
        self,
        message: str,
        code: int = 1,
        status_code: int = 400,
        data: Any = None,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        self.data = data
        super().__init__(message)


class NotFoundError(BusinessError):
    """资源不存在（404）."""

    def __init__(self, message: str = "资源不存在") -> None:
        super().__init__(message, code=404, status_code=404)


class ConflictError(BusinessError):
    """资源冲突，如用户名已存在（409）."""

    def __init__(self, message: str = "资源冲突") -> None:
        super().__init__(message, code=409, status_code=409)


class UnauthorizedError(BusinessError):
    """认证失败（401）."""

    def __init__(self, message: str = "未认证") -> None:
        super().__init__(message, code=401, status_code=401)


class ForbiddenError(BusinessError):
    """权限不足（403）."""

    def __init__(self, message: str = "无权限") -> None:
        super().__init__(message, code=403, status_code=403)
