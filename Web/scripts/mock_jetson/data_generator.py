"""V1 CLI 兼容的数据生成器，底层使用 V2 连续模型。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from scripts.mock_jetson.config import MockConfig
from scripts.mock_jetson.generators import DataBuilder


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class DataGenerator:
    def __init__(self, config: MockConfig) -> None:
        self.config = config
        self.builder = DataBuilder(config)
        self.index = 0
        self.inspection_id = f"INS_LEGACY_{uuid.uuid4().hex[:12].upper()}"

    def generate(
        self,
        data_id: str | None = None,
        inspection_id: str | None = None,
        timestamp: str | None = None,
    ) -> dict:
        count = self.builder.gps.recommended_samples
        sample = self.builder.build(
            inspection_id or self.inspection_id,
            min(self.index, count - 1),
            count,
            timestamp or _now_iso(),
            data_id=data_id,
        )
        self.index += 1
        return sample.payload
