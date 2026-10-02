"""具有惯性的 Jetson 资源指标模拟器。"""
from __future__ import annotations

import random


class DeviceGenerator:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed + 307)
        self.cpu_usage = 24.0
        self.memory_usage = 36.0
        self.cpu_temperature = 48.0
        self.storage_usage = 29.0

    def generate(self, inference_load: bool = False) -> dict:
        target_cpu = 58.0 if inference_load else 28.0
        self.cpu_usage += (target_cpu - self.cpu_usage) * 0.22 + self.rng.uniform(-1.2, 1.2)
        self.memory_usage += ((44.0 if inference_load else 37.0) - self.memory_usage) * 0.08 + self.rng.uniform(-0.25, 0.25)
        temp_target = 45.0 + self.cpu_usage * 0.22
        self.cpu_temperature += (temp_target - self.cpu_temperature) * 0.16 + self.rng.uniform(-0.18, 0.18)
        self.storage_usage = min(95.0, self.storage_usage + (0.012 if inference_load else 0.004))
        return {
            "cpu_temperature": round(self.cpu_temperature, 1),
            "temperature": round(self.cpu_temperature, 1),  # V1 后端字段兼容
            "cpu_usage": round(max(0, min(100, self.cpu_usage)), 1),
            "memory_usage": round(max(0, min(100, self.memory_usage)), 1),
            "storage_usage": round(self.storage_usage, 1),
            "network_status": "online",
        }
