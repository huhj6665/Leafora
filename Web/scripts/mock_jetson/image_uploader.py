"""V1 导入兼容层；实现已迁移到 ``http.uploader``。"""
from scripts.mock_jetson.http_client.uploader import CONTENT_TYPES, DeviceBinder, ImageUploader

_EXT_CONTENT_TYPE = CONTENT_TYPES


def content_type_for(path):
    from pathlib import Path
    return CONTENT_TYPES.get(Path(path).suffix.lower(), "image/jpeg")


__all__ = ["DeviceBinder", "ImageUploader", "content_type_for"]
