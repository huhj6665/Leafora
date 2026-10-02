"""沿确定路线匀速移动的 GPS/RTK 模拟器。"""
from __future__ import annotations

import math

from scripts.mock_jetson.config import MockConfig

EARTH_RADIUS_M = 6_371_000.0


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


class GPSGenerator:
    """起终点之间的平滑曲线路径；位置不做随机游走。"""

    def __init__(self, config: MockConfig) -> None:
        self.config = config
        self.direct_distance_m = distance_m(config.start_lat, config.start_lon, config.end_lat, config.end_lon)

    @property
    def recommended_samples(self) -> int:
        step = max(0.1, self.config.speed_mps * self.config.sample_interval)
        curved_distance = self.direct_distance_m + abs(self.config.route_curve_m) * 1.7
        return max(2, math.ceil(curved_distance / step) + 1)

    def _coordinate(self, progress: float) -> tuple[float, float]:
        t = max(0.0, min(1.0, progress))
        lat = self.config.start_lat + (self.config.end_lat - self.config.start_lat) * t
        lon = self.config.start_lon + (self.config.end_lon - self.config.start_lon) * t
        # 正弦侧向偏移构造连续田间路线，端点偏移为 0。
        dlat = self.config.end_lat - self.config.start_lat
        dlon = self.config.end_lon - self.config.start_lon
        norm = math.hypot(dlat, dlon) or 1.0
        meters_per_lat = 111_320.0
        meters_per_lon = 111_320.0 * math.cos(math.radians(lat))
        curve = math.sin(math.pi * t) * self.config.route_curve_m
        lat += (-dlon / norm) * curve / meters_per_lat
        lon += (dlat / norm) * curve / max(meters_per_lon, 1.0)
        return lat, lon

    def coordinate_at(self, progress: float) -> tuple[float, float]:
        return self._coordinate(progress)

    def generate(self, index: int, sample_count: int) -> dict:
        count = max(2, sample_count)
        progress = min(max(index / (count - 1), 0.0), 1.0)
        lat, lon = self._coordinate(progress)
        before = self._coordinate(max(0.0, progress - 0.001))
        after = self._coordinate(min(1.0, progress + 0.001))
        y = math.sin(math.radians(after[1] - before[1])) * math.cos(math.radians(after[0]))
        x = math.cos(math.radians(before[0])) * math.sin(math.radians(after[0])) - math.sin(math.radians(before[0])) * math.cos(math.radians(after[0])) * math.cos(math.radians(after[1] - before[1]))
        heading = (math.degrees(math.atan2(y, x)) + 360) % 360
        return {
            "latitude": round(lat, 8),
            "longitude": round(lon, 8),
            "altitude_msl_m": round(26.0 + 1.8 * math.sin(progress * math.pi), 2),
            "height_ellipsoid_m": round(42.0 + 1.8 * math.sin(progress * math.pi), 2),
            "fix_quality": 4,
            "rtk_status": "FIXED",
            "satellites_used": 22,
            "horizontal_accuracy_m": 0.018,
            "vertical_accuracy_m": 0.032,
            "ground_speed_mps": round(0.0 if index == count - 1 else self.config.speed_mps, 2),
            "course_over_ground_deg": round(heading, 1),
            "correction_age_s": 0.8,
            "position_valid": True,
        }
