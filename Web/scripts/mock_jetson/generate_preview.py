"""生成并打印模拟 V1.0 JSON 预览（不连接 MQTT，便于核对字段）."""
from __future__ import annotations

import json

from scripts.mock_jetson.config import MockConfig
from scripts.mock_jetson.data_generator import DataGenerator


def preview(config: MockConfig, count: int) -> str:
    generator = DataGenerator(config)
    samples = [generator.generate() for _ in range(count)]
    return json.dumps(samples if count > 1 else samples[0], ensure_ascii=False, indent=2)
