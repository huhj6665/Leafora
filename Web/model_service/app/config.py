"""模型服务配置.

通过环境变量 / .env 注入。权重缺失时服务仍可启动（/health 返回 model_unavailable）。
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    APP_NAME: str = "TLD RT-DETR-L Model Service"
    VERSION: str = "0.1.0"

    MODEL_NAME: str = "RT-DETR-L"
    MODEL_VERSION: str = "v1.0"
    # 权重文件路径（相对 model_service 运行目录或绝对路径）
    MODEL_WEIGHT_PATH: str = "weights/train_best.pt"
    MODEL_DEVICE: str = "cpu"
    MODEL_CONFIDENCE: float = 0.5
    MODEL_IMAGE_SIZE: int = 800

    # 四类检测目标
    CLASS_NAMES: str = "Frogeye,Mosaic,Budworm damage,Wildfire"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
