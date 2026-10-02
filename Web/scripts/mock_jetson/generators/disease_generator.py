"""高斯空间聚集病害模型。"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from scripts.mock_jetson.config import MockConfig
from scripts.mock_jetson.generators.gps_generator import GPSGenerator, distance_m


@dataclass(frozen=True)
class DiseaseCenter:
    latitude: float
    longitude: float
    class_name: str


class DiseaseGenerator:
    def __init__(self, config: MockConfig, gps: GPSGenerator) -> None:
        self.config = config
        self.rng = random.Random(config.random_seed + 203)
        fractions = [(i + 1) / (config.disease_cluster_count + 1) for i in range(config.disease_cluster_count)]
        self.centers = [DiseaseCenter(*gps.coordinate_at(f), config.classes[i % len(config.classes)]) for i, f in enumerate(fractions)]

    def probability(self, latitude: float, longitude: float) -> float:
        values = []
        for center in self.centers:
            d = distance_m(latitude, longitude, center.latitude, center.longitude)
            values.append(self.config.disease_rate * math.exp(-(d * d) / (2 * self.config.disease_sigma_m ** 2)))
        return min(0.98, 0.01 + max(values, default=0.0))

    def generate(self, latitude: float, longitude: float) -> dict:
        probability = self.probability(latitude, longitude)
        if self.rng.random() >= probability:
            return {"has_target": False, "results": [], "probability": round(probability, 4), "count": 0}
        nearest = min(self.centers, key=lambda c: distance_m(latitude, longitude, c.latitude, c.longitude))
        count = 1 + int(self.rng.random() < probability * 0.55) + int(self.rng.random() < probability * 0.25)
        results = []
        for _ in range(count):
            x1, y1 = self.rng.randint(45, 360), self.rng.randint(40, 280)
            width, height = self.rng.randint(70, 210), self.rng.randint(75, 230)
            results.append({
                "class": nearest.class_name,
                "confidence": round(min(0.99, 0.76 + probability * 0.18 + self.rng.uniform(-0.025, 0.025)), 3),
                "bbox": [x1, y1, x1 + width, y1 + height],
            })
        return {"has_target": True, "results": results, "probability": round(probability, 4), "count": count}
