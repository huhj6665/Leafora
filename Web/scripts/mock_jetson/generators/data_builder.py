"""把连续生成器组合为后端兼容 MQTT payload。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from scripts.mock_jetson.config import MockConfig
from scripts.mock_jetson.generators.device_generator import DeviceGenerator
from scripts.mock_jetson.generators.disease_generator import DiseaseGenerator
from scripts.mock_jetson.generators.environment_generator import EnvironmentGenerator
from scripts.mock_jetson.generators.gps_generator import GPSGenerator


@dataclass
class BuiltSample:
    payload: dict
    has_disease: bool
    disease_probability: float


class DataBuilder:
    def __init__(self, config: MockConfig) -> None:
        self.config = config
        self.gps = GPSGenerator(config)
        self.environment = EnvironmentGenerator(config.random_seed)
        self.disease = DiseaseGenerator(config, self.gps)
        self.device = DeviceGenerator(config.random_seed)

    def build(
        self,
        inspection_id: str,
        index: int,
        sample_count: int,
        timestamp: str,
        data_id: str | None = None,
        task: dict | None = None,
        route_point: dict | None = None,
    ) -> BuiltSample:
        location = self.gps.generate(index, sample_count)
        if route_point is not None:
            location.update({
                "latitude": route_point["latitude"], "longitude": route_point["longitude"],
                "course_over_ground_deg": route_point["heading"],
                "ground_speed_mps": 0.0 if index == sample_count - 1 else self.config.speed_mps,
            })
        location["sampled_at"] = timestamp
        disease = self.disease.generate(location["latitude"], location["longitude"])
        environment = self.environment.generate(index * self.config.sample_interval, timestamp)
        environment["valid"] = True
        payload = {
            "schema_version": "1.3" if task else "1.2",
            "device_id": self.config.device_id,
            "inspection_id": inspection_id,
            "data_id": data_id or uuid.uuid4().hex,
            "sequence": index,
            "timestamp": timestamp,
            "location": location,
            "environment": environment,
            "detection": {"has_target": disease["has_target"], "sampled_at": timestamp, "results": disease["results"]},
            "device_status": self.device.generate(disease["has_target"]),
        }
        if task:
            payload.update({
                "field_id": task["field_id"], "field_version": task["field_version"],
                "run_mode": task["run_mode"], "data_provenance": "SIMULATED",
                "flight_status": {"progress": round(index / max(1, sample_count - 1), 4), "phase": "SURVEYING"},
            })
        return BuiltSample(payload=payload, has_disease=disease["has_target"], disease_probability=disease["probability"])
