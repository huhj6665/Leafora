"""Virtual Jetson Simulator V2 配置。

敏感凭据只从环境变量读取；路径默认相对于本包目录解析，避免运行目录变化。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_FILE = PACKAGE_DIR / ".env"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _float(name: str, default: float) -> float:
    return float(_env(name, str(default)) or default)


def _int(name: str, default: int) -> int:
    return int(_env(name, str(default)) or default)


def _bool(name: str, default: bool) -> bool:
    value = _env(name, "true" if default else "false").lower()
    return value in {"1", "true", "yes", "on"}


def mask_secret(secret: str) -> str:
    """Return a troubleshooting-safe secret summary without exposing the credential."""
    if not secret:
        return "<EMPTY>"
    return f"<SET:length={len(secret)}>"


@dataclass
class MockConfig:
    device_id: str = "TLD_JETSON_001"
    device_name: str = "Virtual Jetson"

    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    topic_prefix: str = "tld"
    qos: int = 1

    # 确定性路线参数。center_* 保留给旧 CLI/API 使用。
    center_lat: float = 39.12345678
    center_lon: float = 117.12345678
    start_lat: float = 39.12295
    start_lon: float = 117.12270
    end_lat: float = 39.12402
    end_lon: float = 117.12425
    speed_mps: float = 1.2
    sample_interval: float = 0.5
    route_curve_m: float = 12.0

    # 病害按空间中心聚集；disease_rate 作为中心峰值概率上限，兼容旧参数。
    disease_rate: float = 0.82
    disease_cluster_count: int = 2
    disease_sigma_m: float = 22.0
    random_seed: int = 20260924

    backend_base_url: str = "http://127.0.0.1:8000/api"
    device_secret: str = ""
    disease_images_dir: str = str(PACKAGE_DIR / "images" / "disease")
    normal_images_dir: str = str(PACKAGE_DIR / "images" / "normal")
    test_images_dir: str = str(PACKAGE_DIR / "test_images")  # V1 CLI 兼容
    upload_retries: int = 3
    upload_retry_interval: float = 1.0
    image_every: int = 5
    http_debug: bool = True
    outbox_path: str = str(PACKAGE_DIR / "local" / "outbox.sqlite3")

    @property
    def classes(self) -> tuple[str, ...]:
        return ("Frogeye", "Mosaic", "Budworm damage", "Wildfire")

    def topic(self) -> str:
        return f"{self.topic_prefix}/device/{self.device_id}/data"

    def control_topic(self) -> str:
        return f"{self.topic_prefix}/device/{self.device_id}/control"

    def downlink_topic(self) -> str:
        return f"{self.topic_prefix}/device/{self.device_id}/downlink"

    def status_topic(self) -> str:
        return f"{self.topic_prefix}/device/{self.device_id}/status"

    def ack_topic(self) -> str:
        return f"{self.topic_prefix}/device/{self.device_id}/ack"


def load_config(env_file: str | Path | None = DEFAULT_ENV_FILE) -> MockConfig:
    """Load simulator settings with process environment taking precedence over .env.

    The simulator is normally launched from the repository root, so relying on the
    current working directory would miss ``scripts/mock_jetson/.env``.  Resolve the
    file relative to this module instead.
    """
    if env_file is not None:
        load_dotenv(dotenv_path=Path(env_file), override=False)
    center_lat = _float("MOCK_CENTER_LAT", 39.12345678)
    center_lon = _float("MOCK_CENTER_LON", 117.12345678)
    return MockConfig(
        device_id=_env("MOCK_DEVICE_ID", "TLD_JETSON_001"),
        device_name=_env("MOCK_DEVICE_NAME", "Virtual Jetson"),
        mqtt_host=_env("MQTT_HOST", "127.0.0.1"),
        mqtt_port=_int("MQTT_PORT", 1883),
        mqtt_username=_env("MQTT_USERNAME"),
        mqtt_password=_env("MQTT_PASSWORD"),
        topic_prefix=_env("MQTT_TOPIC_PREFIX", "tld"),
        qos=_int("MQTT_QOS", 1),
        center_lat=center_lat,
        center_lon=center_lon,
        start_lat=_float("MOCK_START_LAT", center_lat - 0.00050678),
        start_lon=_float("MOCK_START_LON", center_lon - 0.00075678),
        end_lat=_float("MOCK_END_LAT", center_lat + 0.00056322),
        end_lon=_float("MOCK_END_LON", center_lon + 0.00079322),
        speed_mps=_float("MOCK_SPEED_MPS", 1.2),
        sample_interval=_float("MOCK_SAMPLE_INTERVAL", 0.5),
        route_curve_m=_float("MOCK_ROUTE_CURVE_M", 12.0),
        disease_rate=max(0.0, min(1.0, _float("MOCK_DISEASE_RATE", 0.82))),
        disease_cluster_count=max(1, _int("MOCK_DISEASE_CLUSTER_COUNT", 2)),
        disease_sigma_m=max(1.0, _float("MOCK_DISEASE_SIGMA_M", 22.0)),
        random_seed=_int("MOCK_RANDOM_SEED", 20260924),
        backend_base_url=_env("TLD_API_BASE_URL", "http://127.0.0.1:8000/api"),
        device_secret=_env("MOCK_DEVICE_SECRET"),
        disease_images_dir=_env("MOCK_DISEASE_IMAGES_DIR", str(PACKAGE_DIR / "images" / "disease")),
        normal_images_dir=_env("MOCK_NORMAL_IMAGES_DIR", str(PACKAGE_DIR / "images" / "normal")),
        test_images_dir=_env("MOCK_TEST_IMAGES_DIR", str(PACKAGE_DIR / "test_images")),
        upload_retries=max(0, _int("MOCK_UPLOAD_RETRIES", 3)),
        upload_retry_interval=max(0.0, _float("MOCK_UPLOAD_RETRY_INTERVAL", 1.0)),
        image_every=max(1, _int("MOCK_IMAGE_EVERY", 5)),
        http_debug=_bool("MOCK_HTTP_DEBUG", True),
        outbox_path=_env("MOCK_OUTBOX_PATH", str(PACKAGE_DIR / "local" / "outbox.sqlite3")),
    )
