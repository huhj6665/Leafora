"""具有缓慢趋势与相关小噪声的环境信号。"""
from __future__ import annotations

import math
import random


class EnvironmentGenerator:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed + 101)
        self.temperature = 25.5
        self.humidity = 58.0
        self.co2 = 438.0
        self.light = 620.0

    def _step(self, value: float, target: float, noise: float) -> float:
        return value + (target - value) * 0.08 + self.rng.gauss(0, noise)

    def generate(self, elapsed_seconds: float, timestamp: str) -> dict:
        phase = elapsed_seconds / 240.0
        self.temperature = self._step(self.temperature, 25.5 + 2.2 * math.sin(phase), 0.07)
        self.humidity = self._step(self.humidity, 58.0 - 4.0 * math.sin(phase), 0.16)
        self.co2 = self._step(self.co2, 438.0 + 22.0 * math.sin(phase * 0.65), 0.8)
        self.light = self._step(self.light, 620.0 + 115.0 * math.sin(phase * 0.8), 4.0)
        return {
            "temperature": round(self.temperature, 1),
            "humidity": round(max(0, min(100, self.humidity)), 1),
            "co2": round(max(300, self.co2), 1),
            "light": round(max(0, self.light), 1),
            "sampled_at": timestamp,
        }
