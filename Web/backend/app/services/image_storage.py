"""图片本地文件系统存储.

存储目录结构（根目录由 IMAGE_STORAGE_ROOT 配置）：
    {root}/images/original/    原始上传图
    {root}/images/annotated/   模型标注图

数据库中仅保存相对 storage key（如 ``images/original/<uuid>.jpg``），
绝不保存 Windows 绝对路径，也不把绝对路径作为公开 URL 返回。
正式部署后可平滑迁移到对象存储。
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import settings

# 允许的图片 MIME 类型与其魔数签名（用于校验真实文件类型）
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
_JPEG_MAGIC = (b"\xff\xd8\xff",)
_PNG_MAGIC = (b"\x89PNG\r\n\x1a\n",)


class InvalidImageError(ValueError):
    """图片校验失败."""


def storage_root() -> Path:
    """解析存储根目录（相对路径基于 backend 运行目录，绝对路径直接用）."""
    root = Path(settings.IMAGE_STORAGE_ROOT)
    return root


def resolve_path(storage_key: str) -> Path:
    """由 storage key 解析绝对路径（禁止路径穿越）."""
    p = (storage_root() / storage_key).resolve()
    # 防止 ../ 逃逸出存储根目录
    if not str(p).startswith(str(storage_root().resolve())):
        raise InvalidImageError("非法存储路径")
    return p


def detect_content_type(data: bytes) -> str | None:
    """根据魔数判定真实图片类型，返回 MIME 或 None."""
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if data.startswith(_PNG_MAGIC):
        return "image/png"
    return None


def validate_image(data: bytes, declared_content_type: str | None = None) -> str:
    """校验图片内容，返回规范化后的 MIME 类型.

    规则：
        - 必须是 JPEG / PNG 真实内容（魔数校验）
        - 声明类型（若提供）必须与真实类型一致
        - 大小不超过 IMAGE_MAX_SIZE_MB
    """
    max_bytes = settings.IMAGE_MAX_SIZE_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise InvalidImageError(f"图片过大，最大 {settings.IMAGE_MAX_SIZE_MB}MB")
    real_type = detect_content_type(data)
    if real_type is None:
        raise InvalidImageError("仅支持 JPEG / PNG 图片")
    if declared_content_type and declared_content_type not in _ALLOWED_CONTENT_TYPES:
        raise InvalidImageError("不支持的文件类型")
    if declared_content_type and declared_content_type != real_type:
        raise InvalidImageError("文件内容与声明类型不一致")
    return real_type


def extension_for(content_type: str) -> str:
    return "jpg" if content_type == "image/jpeg" else "png"


def save_bytes(storage_key: str, data: bytes) -> None:
    """将字节写入存储（自动创建目录）."""
    path = resolve_path(storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def read_bytes(storage_key: str) -> bytes:
    """读取存储文件字节."""
    return resolve_path(storage_key).read_bytes()
